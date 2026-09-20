#!/usr/bin/env python3
"""Publish a dated companion board, preserving all existing architecture edits."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).with_name('publish-home-server-lifecycle-board.py'))
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
board.TITLE = 'Media architecture — Arabic matching & storage — 2026-09-19'
board.PREFIX = 'media-20260919-'

def design():
    b, a, h = board.box, board.arrow, board.heading
    return [
        h('MEDIA / LOCAL ARABIC MATCHING & SHARED STORAGE',0,0),
        h('19 September 2026 • Advisory helper; automatic search adapter remains proposed',0,65,20),
        b('catalog','CATALOG METADATA\nTMDB ID → Radarr lookup\nOriginal title + aliases + year\nNo private media inventory',0,160),
        b('search','PROWLARR / ARABP2P\nSearch original + English titles\nOmit year from tracker query\nAt most two search requests',530,160),
        b('model','ODS / LOCAL QWEN3.5 4B\nLoopback inference only\nUp to 24 sanitized release titles\nNo tracker URLs or API keys',1060,160),
        a('catalog','search'),a('search','model'),
        b('validation','STRICT OUTPUT VALIDATION\nKnown candidate IDs + verdicts only\nExact title / alias and ±1 year gate\nUncertain results stay unresolved',1060,400,470,195),
        b('report','PRIVATE SEARCH REPORT\nSuggestions for review only\nNo download / request permissions\nNo model-driven renaming',530,400,470,195,board.GREEN),
        b('future','PROPOSED NEXT INTEGRATION\nTorznab adapter for Radarr\nNeeds identity / quality validation\nNot connected to normal searches',0,400,470,195,board.AMBER),
        a('model','validation'),a('validation','report'),
        h('DEPLOYED STORAGE & SEEDING POLICY',0,680),
        b('download','QBITTORRENT\nDownload path remains compatible\nStop / pause at ratio 2.0\nActual upload depends on peers',0,755,470,195),
        b('imports','RADARR / SONARR\nOne /data bind mount\nLegacy paths point inside /data\nHardlink imports verified',530,755,470,195),
        b('library','JELLYFIN / MOONFIN\nLibrary link + download link\nShare one underlying file\nExisting duplicates not inspected',1060,755,470,195),
        a('download','imports'),a('imports','library'),
        h('Decisions: local inference, metadata minimization, advisory matching, shared hardlink mount; preserve family identities.',0,1030,18),
        h('Sources: docs/nonenglish-media-matcher.md • docs/media-hardlinks.md • AGENTS.md',0,1075,18),
    ]

board.design = design
if __name__ == '__main__':
    board.main()
