#!/usr/bin/env python3
"""Publish completed, history-matched torrents as Jellyfin versions, without copies.

Run on the server with an explicit Radarr movie ID. Never grabs, deletes, resumes,
or renames torrent data. Incomplete, ambiguous and unmatched releases are skipped.
Only aggregate counts are logged; private paths/hashes stay on the server.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def api(base, headers, path, data=None, method=None):
    req = urllib.request.Request(base + path, headers=headers,
        data=None if data is None else json.dumps(data).encode(), method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        body = response.read()
        return json.loads(body) if body else None


def host_path(path):
    for prefix, root in [('/downloads/', '/mnt/server/media/downloads/'),
                         ('/movies/', '/mnt/server/media/movies/'),
                         ('/data/', '/mnt/server/media/')]:
        if path.startswith(prefix):
            target = Path(root) / path[len(prefix):]
            if target.resolve().is_relative_to(Path(root).resolve()):
                return target
    raise RuntimeError('Unsupported or unsafe media mount')


def physical_pair(a, b):
    """mergerfs virtual inode numbers can differ; verify underlying storage."""
    root = Path('/mnt/server/media')
    pairs = []
    for branch in ['hdd', 'ssd', 'usb-ssd']:
        p = Path('/srv/mergerfs') / branch / 'server/media'
        x, y = p / a.relative_to(root), p / b.relative_to(root)
        if x.exists() and y.exists():
            sa, sb = x.stat(), y.stat()
            pairs.append((sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino))
    return pairs == [True]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--movie-id', required=True, type=int)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--prefer-4k', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('seeding', Path(__file__).with_name('check-seeding-policy.py'))
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    opener = q.qbit_session()
    headers = {'X-Api-Key': ET.parse('/mnt/server/radarr/config/config.xml').getroot().findtext('ApiKey'),
               'Content-Type': 'application/json'}
    def rad(path, data=None, method=None):
        return api('http://127.0.0.1:7878/api/v3', headers, path, data, method)
    movie = rad('/movie/' + str(args.movie_id))
    assert movie.get('hasFile'), 'Wait for Radarr to import its preferred version'
    history = rad('/history/movie?movieId=' + str(args.movie_id))
    matched = {}
    for event in history:
        if event.get('downloadId') and event.get('quality', {}).get('quality', {}).get('resolution'):
            matched[event['downloadId'].lower()] = event['quality']['quality']['resolution']
    folder = host_path(movie['path'] + '/')
    master = folder / movie['movieFile']['relativePath']
    plans = []
    jobs = q.get_json(q.QBIT_URL + '/api/v2/torrents/info', opener=opener)
    for job in jobs:
        if job['hash'].lower() not in matched or job['progress'] < 1:
            continue
        files = q.get_json(q.QBIT_URL + '/api/v2/torrents/files?hash=' + job['hash'], opener=opener)
        videos = [f for f in files if Path(f['name']).suffix.lower() in ('.mkv', '.mp4', '.avi', '.m4v')]
        if len(videos) != 1 or videos[0]['progress'] < 1:
            continue
        source = host_path(job['save_path'].rstrip('/') + '/' + videos[0]['name'])
        assert source.is_file() and source.stat().st_size == videos[0]['size'], 'Incomplete source'
        if physical_pair(source, master):
            destination = master
        else:
            destination = folder / (folder.name + ' - ' + str(matched[job['hash'].lower()]) + 'p' + source.suffix)
        if destination.exists():
            assert physical_pair(source, destination), 'Version name collision; no files changed'
        plans.append((source, destination))
    assert len(plans) >= 2, 'Need at least two completed, unambiguous history-matched versions'
    assert len({b for a, b in plans}) == len(plans), 'Ambiguous duplicate resolution'
    print('PASS completed matched versions:', len(plans))
    if not args.apply:
        return
    state = Path.home() / '.local/state/home-server-maintenance/movie-versions' / str(args.movie_id)
    state.mkdir(parents=True, exist_ok=True)
    backup = state / ('before-' + str(time.time_ns()) + '.json')
    backup.write_text(json.dumps({'movie': movie, 'links': [[str(a), str(b)] for a, b in plans]}))
    for source, destination in plans:
        if not destination.exists():
            os.link(source, destination)  # No copy fallback; cross-device failure is safe.
        assert physical_pair(source, destination), 'Physical hardlink verification failed'
    if args.prefer_4k:
        name = 'Home 1080p + 4K (prefer 4K)'
        profiles = rad('/qualityprofile')
        profile = next((p for p in profiles if p['name'] == name), None)
        if profile is None:
            profile = rad('/qualityprofile/' + str(movie['qualityProfileId']))
            profile.pop('id', None)
            profile.update(name=name, upgradeAllowed=True, cutoff=1003)
            def enable(item):
                children = item.get('items', [])
                if children:
                    for child in children:
                        enable(child)
                    item['allowed'] = any(c['allowed'] for c in children)
                else:
                    quality = item['quality']
                    item['allowed'] = quality['resolution'] in (1080, 2160) and quality['source'] in ('webdl', 'webrip', 'bluray') and quality['modifier'] == 'none'
            for item in profile['items']:
                enable(item)
            assert any(i.get('id') == 1003 and i['allowed'] for i in profile['items'])
            profile = rad('/qualityprofile', profile, 'POST')
        movie['qualityProfileId'] = profile['id']
        rad('/movie/' + str(args.movie_id), movie, 'PUT')
    settings = json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text())
    jh = {'X-Emby-Token': settings['jellyfin']['apiKey'], 'Content-Type': 'application/json'}
    def jelly(path, data=None, method=None):
        return api('http://127.0.0.1:8096', jh, path, data, method)
    users = jelly('/Users')
    owner = next(u for u in users if u['Name'] == 'egouda')
    library_folder = '/data/movies/' + folder.name
    def items(user=owner):
        # Unscoped admin /Items includes hidden alternate-version records.
        # The user library is the view actually used by Moonfin.
        result = jelly('/Users/' + user['Id'] + '/Items?Recursive=true&IncludeItemTypes=Movie&Fields=MediaSources,ProviderIds,Path')
        return [i for i in result['Items'] if str(Path(i.get('Path', '')).parent) == library_folder]
    jelly('/Library/Refresh', method='POST')
    for attempt in range(60):
        records = items()
        paths = {s['Path'] for i in records for s in i.get('MediaSources', [])}
        expected = {library_folder + '/' + b.name for a, b in plans}
        if expected <= paths:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Library scan pending; safe to rerun')
    if len(records) > 1:
        # Jellyfin selects the highest-resolution video as primary when merging.
        jelly('/Videos/MergeVersions?ids=' + ','.join(i['Id'] for i in records), method='POST')
    records = items()
    assert len(records) == 1, 'Expected one movie after merge'
    sources = records[0]['MediaSources']
    assert len(sources) == len(plans), 'Version count differs'
    widths = [max((s.get('Width', 0) for s in media.get('MediaStreams', []) if s['Type'] == 'Video'), default=0) for media in sources]
    assert widths[0] == max(widths) and widths[0] > 1920, '4K must be preferred'
    family = next((u for u in users if u['Name'] == 'mgouda'), None)
    if family:
        family_items = items(family)
        assert len(family_items) == 1 and len(family_items[0]['MediaSources']) == len(plans), 'Family library versions differ'
    after = q.get_json(q.QBIT_URL + '/api/v2/torrents/info', opener=opener)
    assert {t['hash'] for t in jobs} <= {t['hash'] for t in after}, 'Torrent retention changed'
    print('PASS single Jellyfin movie, versions=', len(sources), 'preferred=4K; physical hardlinks verified; all torrents retained')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Library paths and tracker identifiers must never enter logs.
        print('FAIL movie version synchronization:', type(exc).__name__,
              str(exc) if isinstance(exc, AssertionError) else '(details withheld)')
        raise SystemExit(1)
