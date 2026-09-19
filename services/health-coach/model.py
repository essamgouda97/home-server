"""Deterministic coach-sheet projection. No personal source data belongs here."""
import re

STACK = [(9.1,4.5),(13.6,6.8),(18.1,9.1),(22.7,11.3),(27.2,13.6),
         (31.8,15.9),(36.3,18.1),(40.8,20.4),(45.4,22.7),(49.9,24.9),
         (54.4,27.2),(59.0,29.5),(63.5,31.8),(68.0,34.0),(72.6,36.3),(77.1,38.6)]
RANGES = ["'Training'!A1:Q160", "'شيت التغذية'!A1:Z150",
          "'Log book'!A1:GP120", "'شيت المتابعة'!A1:AD110",
          "'شيت المكملات'!A1:Z70", "'تبديلات الاكل و الوصفات'!A1:Z100"]


def column(n):
    result = ''
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def ref(title, row, col):
    return "'" + title.replace("'", "''") + "'!" + column(col) + str(row)


def sheets(raw):
    result = {}
    for document in raw if isinstance(raw, list) else [raw]:
        for sheet in document.get('sheets', []):
            if sheet.get('data'):
                result[sheet['properties']['title']] = sheet
    return result


def cell(sheet, row, col):
    for block in sheet.get('data', []):
        r, c = row - 1 - block.get('startRow', 0), col - 1 - block.get('startColumn', 0)
        rows = block.get('rowData', [])
        if 0 <= r < len(rows):
            values = rows[r].get('values', [])
            if 0 <= c < len(values):
                return values[c]
    return {}


def text(sheet, row, col):
    return cell(sheet, row, col).get('formattedValue', '').strip()


def entered(c):
    v = c.get('userEnteredValue', {})
    return next(iter(v.values()), '')


def number(s):
    s = str(s).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
    found = re.search(r'\d+(?:\.\d+)?', s)
    return float(found[0]) if found else None


def projection(raw):
    source = sheets(raw)
    required = {'Training', 'Log book', 'شيت التغذية', 'شيت المتابعة'}
    if not required.issubset(source):
        raise ValueError('The expected coach tabs are missing. Review sheet mapping.')
    training, log, nutrition, check = [source[t] for t in ['Training','Log book','شيت التغذية','شيت المتابعة']]
    if text(log,4,3) != 'Exercise' or text(check,1,4) != 'AVG Bodyweight':
        raise ValueError('The sheet layout changed. Review mapping before syncing.')
    out = {'workouts': [], 'meals': [], 'checkins': [], 'writable': {},
           'rules': [], 'nutritionRules': [], 'supplements': [], 'recipes': [],
           'substitutions': [], 'warnings': [], 'rotation': [], 'cardio': []}

    def writable(title, r, c, kind, identity, label):
        data = cell(source[title], r, c)
        if 'formulaValue' in data.get('userEnteredValue', {}):
            return None
        address = ref(title, r, c)
        options = [v.get('userEnteredValue') for v in data.get('dataValidation', {}).get('condition', {}).get('values', [])]
        out['writable'][address] = {'value': entered(data), 'kind': kind, 'identity': identity,
                                    'label': label, 'options': options}
        return address

    for c in range(4,18,2):
        out['rotation'].append(text(training,8,c))
    for r in [17,20,21,22]:
        out['rules'].append(text(training,r,3))
    for r in [120,122]:
        out['cardio'].append({'when': text(training,r,3), 'intensity': text(training,r,7),
                              'duration': text(training,r,8), 'notes': text(training,r,9)})
    for r in range(8,25):
        if text(nutrition,r,10): out['nutritionRules'].append(text(nutrition,r,10))

    # Exercise identities come from formula references, not fuzzy name matching.
    group = None
    for r in range(4,115):
        if text(log,r,1) and text(log,r,3) == 'Exercise':
            group = {'name': text(log,r,1), 'exercises': [], 'slots': []}
            for c in range(9,199):
                if text(log,r,c) == 'Set 1' and text(log,r+1,c) == 'kg':
                    group['slots'].append({'index':len(group['slots'])+1,'column':c})
            out['workouts'].append(group)
        if not group or not text(log,r,3) or not text(log,r,2).isdigit(): continue
        formula = cell(log,r,3).get('userEnteredValue',{}).get('formulaValue','')
        match = re.fullmatch(r'=Training!D(\d+)', formula)
        if not match: raise ValueError('Unrecognized exercise source; mapping needs review.')
        tr = int(match[1]); name = text(log,r,3)
        item = {'id':f'training-{tr}', 'row':r, 'name':name, 'sets':text(log,r,5),
                'reps':text(log,r,6), 'rest':text(log,r,7), 'restSeconds':number(text(log,r,7)) or 60,
                'timed': 'ثانية' in text(log,r,6), 'warmup':text(training,tr,9),
                'notes':text(training,tr,14), 'video':cell(training,tr,8).get('hyperlink',''), 'history':[]}
        if not item['video'] and text(training,tr,1).startswith('https://'): item['video']=text(training,tr,1)
        for slot in group['slots']:
            pairs = []
            for n in range(5):
                c = slot['column'] + n*2
                if text(log, (4 if group['name']=='Push' else 17 if group['name']=='Pull' else 30 if group['name']=='Legs' else 41)+1,c) != 'kg':
                    raise ValueError('Set column layout changed.')
                identity = f'{group["name"]}:{name}:{slot["index"]}:{n+1}'
                kg = writable('Log book',r,c,'kg',identity+':kg',name+' kg')
                reps = writable('Log book',r,c+1,'seconds' if item['timed'] else 'reps',identity+':reps',name+' repetitions / seconds')
                pairs.append({'kg':kg,'reps':reps})
            item['history'].append(pairs)
        group['exercises'].append(item)

    meal = None
    for r in range(7,70):
        if text(nutrition,r,2) and text(nutrition,r,2) != 'الوجبة':
            meal={'id':f'meal-{r}','name':text(nutrition,r,2), 'dayType':'training' if r<43 else 'rest','ingredients':[]}
            out['meals'].append(meal)
        content=text(nutrition,r,3)
        if meal and content and content != 'المكونات':
            meal['ingredients'].append({'id':f'ingredient-{r}','text':content,'notes':text(nutrition,r,7),
                                        'options':re.split(r'\s+او\s+',content)})
    for r in range(2,111):
        date=text(check,r,3)
        if not re.fullmatch(r'\d{4}/\d{2}/\d{2}',date): continue
        item={'row':r,'date':date.replace('/','-'),'week':text(check,r,2),'fields':[]}
        for c in range(6,19):
            kind='weight' if c<=8 else 'text'
            address=writable('شيت المتابعة',r,c,kind,date+':'+text(check,1,c),text(check,1,c))
            item['fields'].append({'ref':address,'label':text(check,1,c),'kind':kind})
        out['checkins'].append(item)
    supplement=source.get('شيت المكملات',{})
    for r in range(3,8):
        if text(supplement,r,2):out['supplements'].append({'name':text(supplement,r,2),'type':text(supplement,r,6),'dose':text(supplement,r,11),'timing':text(supplement,r,15)})
    swaps=source.get('تبديلات الاكل و الوصفات',{})
    for r in range(3,100):
        for a,b in [(1,2),(4,5),(7,8),(10,11)]:
            if text(swaps,r,a) and text(swaps,r,b):out['substitutions'].append({'from':text(swaps,r,a),'to':text(swaps,r,b)})
        if text(swaps,r,13).startswith('https://'):out['recipes'].append({'name':text(swaps,r,14),'url':text(swaps,r,13)})
    for title,sheet in source.items():
        for block in sheet.get('data',[]):
            for r,row in enumerate(block.get('rowData',[]),1):
                for c,data in enumerate(row.get('values',[]),1):
                    if data.get('effectiveValue',{}).get('errorValue') and title=='Log book':
                        out['warnings'].append({'ref':ref(title,r,c),'message':'Existing spreadsheet formula error'})
    return out
