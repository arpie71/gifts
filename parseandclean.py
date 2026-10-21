import pandas as pd
import os
import re
import numpy as np


# FUNCTIONS
# Function to extract and clean the columns
def extract_and_clean(df, column_name, regex_pattern, replace_pattern):
    """ 
    Takes a regex pattern and replacement pattern and changes the elements of a pandas dataframe
    
    Args:
        df: Dataframe to use
        column_name: Name of new column to add
        regex_pattern: regex pattern to look for 
        replace_pattern: what to replace regex pattern with 
        find_str: The tag to search for and return the text from

    """
    df['itemt']=df.item
    df[[ 'item', column_name]] = df['item'].str.extract(regex_pattern, flags=re.M)
    df[column_name] = df[column_name].str.replace(replace_pattern, '', regex=True).str.strip()
    df[column_name] = df[column_name].str.replace(r'.$','', regex=True)
    df['item'] = df['item'].fillna(df['itemt'])

def fix_encoding(s):
    if isinstance(s, str):
        try:
            return s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            return s
    return s

def fix_mojibake(s):
    if pd.isna(s):
        return s
    try:
        return s.encode('cp1252').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

def assign_officeholder(year, role):
    if pd.isna(year):
        return None
    for name, years in ROLES[role].items():
        if years["startyear"] <= int(year) <= years["endyear"]:
            return name
    return None

def fill_role_wikidata(df):
    df = df.copy()
    for role in ROLES:
        holder_col = role.lower().replace(" ", "_")  # "president", "vice_president", "first_lady"
        df[holder_col] = df["year"].apply(lambda y: assign_officeholder(y, role))
        mask = (df["recip"] == role) & df[holder_col].notna()
        df.loc[mask, "recip_wiki"] = df.loc[mask, holder_col].map(lambda name: ROLES[role][name]["WikidataID"])
    return df
    

# LISTS and CONSTANTS
ROLES = {
    "President": {
        "Clinton": {"startyear": 1993, "endyear": 2000, "WikidataID": "Q1124"},
        "Bush":    {"startyear": 2001, "endyear": 2008, "WikidataID": "Q207"},
        "Obama":   {"startyear": 2009, "endyear": 2016, "WikidataID": "Q76"},
        "Trump1":  {"startyear": 2017, "endyear": 2020, "WikidataID": "Q22686"},
        "Biden":   {"startyear": 2021, "endyear": 2024, "WikidataID": "Q6279"},
        "Trump2":  {"startyear": 2025, "endyear": 2028, "WikidataID": "Q22686"},
    },
    "Vice President": {
        "Gore":    {"startyear": 1993, "endyear": 2000, "WikidataID": "Q19673"},
        "Cheney":  {"startyear": 2001, "endyear": 2008, "WikidataID": "Q48589"},
        "Biden":   {"startyear": 2009, "endyear": 2016, "WikidataID": "Q6279"},
        "Pence":   {"startyear": 2017, "endyear": 2020, "WikidataID": "Q24313"},
        "Harris":  {"startyear": 2021, "endyear": 2024, "WikidataID": "Q10853588"},
        "Vance":   {"startyear": 2025, "endyear": 2028, "WikidataID": "Q31791"},
    },
    "First Lady": {
        "Clinton": {"startyear": 1993, "endyear": 2000, "WikidataID": "Q6294"},
        "Bush":    {"startyear": 2001, "endyear": 2008, "WikidataID": "Q233942"},   # Laura Bush
        "Obama":   {"startyear": 2009, "endyear": 2016, "WikidataID": "Q13133"},    # Michelle Obama
        "Trump1":  {"startyear": 2017, "endyear": 2020, "WikidataID": "Q191807"},   # Melania Trump
        "Biden":   {"startyear": 2021, "endyear": 2024, "WikidataID": "Q4726723"},  # Jill Biden
        "Trump2":  {"startyear": 2025, "endyear": 2028, "WikidataID": "Q191807"},   # Melania Trump
    },
}



wiki = pd.read_csv('files/masterwiki_new.csv', encoding='utf-8-sig')
#wiki = wiki.apply(lambda col: col.map(fix_encoding))
wiki['entity'] = wiki['entity'].apply(fix_mojibake)


if not os.path.isdir('cleaned'):
    os.mkdir('cleaned')

files = os.listdir('raw')
ranklist = ['General','Admiral','Captain','Ambassador','Colonel','Commander','Major','Sergeant','Special Agent']
rank_pattern = r'((.+)?\s*(' + '|'.join(ranklist) + '))'
poslist = ['Vice President','White House Staff Member','Senator','Former President','President']
pos_pattern = r'((.+)?\s*(' + '|'.join(poslist)+'))'
#giverranklist = ['General','Admiral','Captain','Ambassador','Colonel','Commander','Major','Sergeant','Marshal','Marshall']
giverranklist = ['General','Admiral','Captain','Ambassador','Colonel','Commander','Major','Sergeant','Marshal(l | )']
giverrank_pattern = r'((.+)?\s*(' + '|'.join(giverranklist)+'))'
excllist = ['5 U.S.C. 7342(f)(4)', 'Foreign Government Official', 'Unknown','An Agency Employee', 'Unknown', '5 U.S.C. 7342 (f)(4)',  '5 U.S.C. § 7342(f)(4)','5USC 7342 (f)(4)','5 U.S.C.  7342(f)(4)','50 U.S.C. 403-(1)(i)','Government Official','U.S. Air Force Employee','Employee of the Department of State','Department of State employee','USAID Employee','Unknown Foreign Government Official Donor','Unknown Qatar Government Official','5 U.S.C. 7342(F)(4)','5 U.S.C. 7342(f)4)','5USC 7342 (f)(4).','5USC 7342(f)(4)']

giver_remove = ['His Excellency','Her Excellency','His Majesty','Her Majesty','The Right Honorable','The Most Honorable','His Majesty','His Royal Highness','His Highness','President','Her Highness','Her Royal Highness','His Holiness','Senator','Madame',r'H\.M\.',r'H\. E\.',r'T\.H\.','First Lady','Chief of General Staff']
giverremove_pattern = r'((.+)?\s*(' + '|'.join(giver_remove)+'))'


with open('files/nowiki2.txt','r') as f:
    nowikilist = f.read().splitlines()

excllist.extend(nowikilist)
#excllist=filter(None,excllist)

groupgivers = pd.read_csv('files/groups.csv')


for filename in files:
    df = pd.read_csv('raw/' + filename, encoding='utf-8-sig')
    df['item'] = df.item.str.strip()
    # Save the original item
    df['item_orig'] = df['item']
    df['recip'] = df.recip.str.strip()
    df['recip'] = df['recip'].replace('',np.nan)
    df.loc[:,'recip']=df.loc[:,'recip'].ffill()
    df['giver'] = df.giver.str.strip()
    df['giver'] = df['giver'].replace('',np.nan)
    df['giver'] = df['giver'].replace('^His Excellency[,.]','His Excellency', regex=True)
    df['giver'] = df['giver'].replace('^His Majesty,','His Majesty', regex=True)
    df['giver'] = df['giver'].replace('^Chief of General Staff,','Chief of General Staff', regex=True)
    df['giver'] = df['giver'].replace('^Lieutenant General Staff,','Lieutenant General Staff', regex=True)
    df['giver'] = df['giver'].replace('^The Honorable,','The Honorable', regex=True)
    df['giver'] = df['giver'].replace('^His Royal Highness[,.]','His Royal Highness', regex=True)
    df['giver'] = df['giver'].replace('^His Highness,','His Highness', regex=True)
    df['giver'] = df['giver'].replace('^His Holiness,','His Holiness', regex=True)
    df.loc[:,'giver']=df.loc[:,'giver'].ffill()
    # Disposition extraction
    extract_and_clean(df, 'disposition', r'(.+)(Disposition.+$)', r'Disposition—')
    # Location extraction
    extract_and_clean(df, 'location', r'(.+)(Location.+$)', r'Location—')
    # Estval extraction
    extract_and_clean(df, 'estval', r'(.+)(Est.+$|[Aa]ppraised+$)', r'Est. Value—')
    # Recd extraction
    extract_and_clean(df, 'recd', r'(.+)(Rec\'d.+$)', r'Rec\'d—')
    # Replace 'item' with 'item_orig' where 'item' is missing, then clean the 'item'
    df['item'] = df['item'].fillna(df['item_orig']).str.strip().str.replace(r'\.$', '', regex=True)
    # parsing recipient
    df[['recip_name','recip_title','recip_org']]=df['recip'].str.split(',', n=2, expand=True)
    df['recip_name'] = df.recip_name.str.replace(r'(T\.H\.|The Honorable|Mr\.|Ms\.|Dr\.|Mrs\.|First Daughter|First Lady) ','',regex=True)
    #df['recip_rank'] = df['recip_name'].str.extract(r'((.+)?\s*(General|Admiral|Captain))', expand=False)[0]
    #df['recip_name'] = df['recip_name'].str.replace(r'((.+)?\s*(General|Admiral|Captain))','',regex=True).str.strip()
    df['recip_rank'] = df['recip_name'].str.extract(rank_pattern, expand=False)[0]
    df['recip_name'] = df['recip_name'].str.replace(rank_pattern,'',regex=True).str.strip()
    df['recip_t'] = df['recip_name'].str.extract(pos_pattern, expand=False)[0]
    df['recip_name'] = df['recip_name'].str.replace(pos_pattern,'',regex=True).str.strip()
    df['recip_title'] = df['recip_title'].fillna(df['recip_t'])
    # parsing giver
    df[['giver_name','giver_title','giver_org']]=df['giver'].str.split(', ', n=2, expand=True)
    df['giver_name'] = df.giver_name.str.replace(r'(The Honorable|Mr\.|Ms\.|Mrs\.|Dr\.|H\.E\.|H\.R\.H\.|His Excellence|His Excellency) ','',regex=True)
    #df['giver_name'] = df.giver_name.str.replace('(His Excellency|Her Excellency|His Majesty|Her Majesty|The Right Honorable|The Most Honorable) ','',regex=True)
    df['giver_rank'] = df['giver_name'].str.extract(giverrank_pattern, expand=False)[0]
    df['giver_name'] = df['giver_name'].str.replace(giverrank_pattern,'',regex=True).str.strip()
    df['giver_title2'] = df['giver_name'].str.extract(giverremove_pattern, expand=False)[0]
    df['giver_name'] = df['giver_name'].str.replace(giverremove_pattern,'',regex=True).str.strip()
    #df['giver_rank'] = df['giver_name'].str.extract(r'((.+)?\s*(General|Admiral|Captain|Ambassador))', expand=False)[0]
    #df['giver_name'] = df['giver_name'].str.replace(r'((.+)?\s*(General|Admiral|Captain|Ambassador))','',regex=True).str.strip() 
    # stripping spaces for all string variables
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    # merging in wiki with recipient
    # --- first merge: match on recip_name ---
    df = df.merge(wiki, left_on='recip_name', right_on='entity', how='left')
    df = df.drop(columns='entity')
    # --- second merge: match on recip, values get '_upd' suffix ---
    df = df.merge(wiki, left_on='recip', right_on='entity', how='left', suffixes=('', '_upd'))
    df = df.drop(columns='entity')
    # --- "update replace": where second merge found a match, it wins; else keep first ---
    for col in ['wiki', 'wikiname', 'descr']:
        upd_col = f'{col}_upd'
        df[col] = df[upd_col].where(df[upd_col].notna(), df[col])
        df = df.drop(columns=upd_col)
    # --- final rename ---
    df = df.rename(columns={'wiki': 'recip_wiki', 'wikiname': 'recip_wikiname', 'descr': 'recip_descr'})

    #df = pd.merge(df,wiki, left_on= 'recip_name', right_on='entity',how='left')
    #df = df.rename(columns = {"wiki":"recip_wiki","wikiname":"recip_wikiname","descr":"recip_descr"})
    df = df.drop(columns= ['itemt','recip_t'])
    df.loc[df['recip_name'].isin(excllist), 'recip_wiki'] = 'NIL'
    #df.loc[((df.recip_name=='An Agency Employee')|(df.recip_name=='Unknown')|(df.recip_name=='5 U.S.C. 7342 (f)(4)')|(df.recip_name=='5 U.S.C. 7342(f)(4)')|(df.recip_name=='5 U.S.C. § 7342(f)(4)')),'recip_wiki']='NIL'
    # merging in wiki with giver
    # --- first merge: match on giver_name ---
    df = df.merge(wiki, left_on='giver_name', right_on='entity', how='left')
    df = df.drop(columns='entity')
    # --- second merge: match on giver, values get '_upd' suffix ---
    df = df.merge(wiki, left_on='giver', right_on='entity', how='left', suffixes=('', '_upd'))
    df = df.drop(columns='entity')
    # --- "update replace": where second merge found a match, it wins; else keep first ---
    for col in ['wiki', 'wikiname', 'descr']:
        upd_col = f'{col}_upd'
        df[col] = df[upd_col].where(df[upd_col].notna(), df[col])
        df = df.drop(columns=upd_col)
    # --- final rename ---
    df = df.rename(columns={'wiki': 'giver_wiki', 'wikiname': 'giver_wikiname', 'descr': 'giver_descr'})
    #df = pd.merge(df,wiki, left_on= 'giver_name', right_on='entity',how='left')
    #df = df.rename(columns = {"wiki":"giver_wiki","wikiname":"giver_wikiname","descr":"giver_descr"})
    #df = df.drop(columns= ['entity'])
    df.loc[df['giver_name'].isin(excllist), 'giver_wiki'] = 'NIL'
    df = pd.merge(df,groupgivers, left_on='giver',right_on='giver_orig',how='left')
    mask = df['WikidataID'].notna() & (df['WikidataID'] != '')
    df.loc[mask, 'giver_wiki'] = df['WikidataID']
    df = df.drop(columns= ['giver_orig','WikidataID'])
    #df.loc[((df.giver_name=='5 U.S.C. 7342(f)(4)')|(df.giver_name=='Foreign Government Official')|(df.giver_name=='Unknown')),'giver_wiki']='NIL'
    df.loc[df.giver_name.str.contains(r'^Unknown\b', na=False), 'giver_wiki'] = 'NIL'
    df = pd.merge(df,groupgivers, left_on='recip',right_on='giver_orig',how='left')
    mask = df['WikidataID'].notna() & (df['WikidataID'] != '')
    df.loc[mask, 'recip_wiki'] = df['WikidataID']
    df = fill_role_wikidata(df)
    df = df.drop(columns= ['giver_orig','WikidataID','president','first_lady','vice_president'])
    # stripping spaces for all string variables
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    # saving cleaned data
    df.to_csv('cleaned/'+filename, index=False)




