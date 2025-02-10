import pandas as pd
import os
import re
import numpy as np

# Function to extract and clean the columns
def extract_and_clean(df, column_name, regex_pattern, replace_pattern):
	df['itemt']=df.item
	df[[ 'item', column_name]] = df['item'].str.extract(regex_pattern, flags=re.M)
	df[column_name] = df[column_name].str.replace(replace_pattern, '', regex=True).str.strip()
	df[column_name] = df[column_name].str.replace(r'.$','', regex=True)
	df['item'] = df['item'].fillna(df['itemt'])

wiki = pd.read_csv('files/masterwiki.csv')

files = os.listdir('raw2')
ranklist = ['General','Admiral','Captain','Ambassador','Colonel','Commander','Major','Sergeant','Special Agent']
rank_pattern = r'((.+)?\s*(' + '|'.join(ranklist) + '))'
poslist = ['Vice President','White House Staff Member','Senator','Former President','President']
pos_pattern = r'((.+)?\s*(' + '|'.join(poslist)+'))'
#giverranklist = ['General','Admiral','Captain','Ambassador','Colonel','Commander','Major','Sergeant','Marshal','Marshall']
giverranklist = ['General','Admiral','Captain','Ambassador','Colonel','Commander','Major','Sergeant','Marshal(l | )']
giverrank_pattern = r'((.+)?\s*(' + '|'.join(giverranklist)+'))'
excllist = ['5 U.S.C. 7342(f)(4)', 'Foreign Government Official', 'Unknown','An Agency Employee', 'Unknown', '5 U.S.C. 7342 (f)(4)',  '5 U.S.C. § 7342(f)(4)','5USC 7342 (f)(4)','5 U.S.C.  7342(f)(4)','50 U.S.C. 403-(1)(i)','Government Official','U.S. Air Force Employee','Employee of the Department of State','Department of State employee','USAID Employee','Unknown Foreign Government Official Donor','Unknown Qatar Government Official']

for filename in files:
    df = pd.read_csv('raw2/' + filename)
    df['item'] = df.item.str.strip()
    # Save the original item
    df['item_orig'] = df['item']
    df['recip'] = df.recip.str.strip()
    df['recip'] = df['recip'].replace('',np.nan)
    df.loc[:,'recip']=df.loc[:,'recip'].ffill()
    df['giver'] = df.giver.str.strip()
    df['giver'] = df['giver'].replace('',np.nan)
    df['giver'] = df['giver'].replace('^His Excellency,','His Excellency', regex=True)
    df['giver'] = df['giver'].replace('^His Majesty,','His Majesty', regex=True)
    df['giver'] = df['giver'].replace('^His Royal Highness,','His Royal Highness', regex=True)
    df['giver'] = df['giver'].replace('^His Highness,','His Highness', regex=True)
    df.loc[:,'giver']=df.loc[:,'giver'].ffill()
    # Disposition extraction
    extract_and_clean(df, 'disposition', r'(.+)(Disposition.+$)', r'Disposition—')
    # Location extraction
    extract_and_clean(df, 'location', r'(.+)(Location.+$)', r'Location—')
    # Estval extraction
    extract_and_clean(df, 'estval', r'(.+)(Est.+$)', r'Est. Value—')
    # Recd extraction
    extract_and_clean(df, 'recd', r'(.+)(Rec\'d.+$)', r'Rec\'d—')
    # Replace 'item' with 'item_orig' where 'item' is missing, then clean the 'item'
    df['item'] = df['item'].fillna(df['item_orig']).str.strip().str.replace(r'\.$', '', regex=True)
    # parsing recipient
    df[['recip_name','recip_title','recip_org']]=df['recip'].str.split(',', n=2, expand=True)
    df['recip_name'] = df.recip_name.str.replace('(T\.H\.|The Honorable|Mr\.|Ms\.|Dr\.|Mrs\.|First Daughter|First Lady) ','',regex=True)
    #df['recip_rank'] = df['recip_name'].str.extract(r'((.+)?\s*(General|Admiral|Captain))', expand=False)[0]
    #df['recip_name'] = df['recip_name'].str.replace(r'((.+)?\s*(General|Admiral|Captain))','',regex=True).str.strip()
    df['recip_rank'] = df['recip_name'].str.extract(rank_pattern, expand=False)[0]
    df['recip_name'] = df['recip_name'].str.replace(rank_pattern,'',regex=True).str.strip()
    df['recip_t'] = df['recip_name'].str.extract(pos_pattern, expand=False)[0]
    df['recip_name'] = df['recip_name'].str.replace(pos_pattern,'',regex=True).str.strip()
    df['recip_title'] = df['recip_title'].fillna(df['recip_t'])
    # parsing giver
    df[['giver_name','giver_title','giver_org']]=df['giver'].str.split(', ', n=2, expand=True)
    df['giver_name'] = df.giver_name.str.replace('(The Honorable|Mr\.|Ms\.|Mrs\.|Dr\.|H\.E\.|H\.R\.H\.) ','',regex=True)
    df['giver_name'] = df.giver_name.str.replace('(His Excellency|Her Excellency|His Majesty|Her Majesty|The Right Honorable|The Most Honorable) ','',regex=True)
    df['giver_rank'] = df['giver_name'].str.extract(giverrank_pattern, expand=False)[0]
    df['giver_name'] = df['giver_name'].str.replace(giverrank_pattern,'',regex=True).str.strip()
    #df['giver_rank'] = df['giver_name'].str.extract(r'((.+)?\s*(General|Admiral|Captain|Ambassador))', expand=False)[0]
    #df['giver_name'] = df['giver_name'].str.replace(r'((.+)?\s*(General|Admiral|Captain|Ambassador))','',regex=True).str.strip() 
    # stripping spaces for all string variables
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    # merging in wiki with recipient
    df = pd.merge(df,wiki, left_on= 'recip_name', right_on='entity',how='left')
    df = df.rename(columns = {"wiki":"recip_wiki","wikiname":"recip_wikiname","descr":"recip_descr"})
    df = df.drop(columns= ['itemt','entity','recip_t'])
    df.loc[df['recip_name'].isin(excllist), 'recip_wiki'] = 'NIL'
    #df.loc[((df.recip_name=='An Agency Employee')|(df.recip_name=='Unknown')|(df.recip_name=='5 U.S.C. 7342 (f)(4)')|(df.recip_name=='5 U.S.C. 7342(f)(4)')|(df.recip_name=='5 U.S.C. § 7342(f)(4)')),'recip_wiki']='NIL'
    # merging in wiki with giver
    df = pd.merge(df,wiki, left_on= 'giver_name', right_on='entity',how='left')
    df = df.rename(columns = {"wiki":"giver_wiki","wikiname":"giver_wikiname","descr":"giver_descr"})
    df = df.drop(columns= ['entity'])
    df.loc[df['giver_name'].isin(excllist), 'giver_wiki'] = 'NIL'
    #df.loc[((df.giver_name=='5 U.S.C. 7342(f)(4)')|(df.giver_name=='Foreign Government Official')|(df.giver_name=='Unknown')),'giver_wiki']='NIL'
    # stripping spaces for all string variables
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    # saving cleaned data
    df.to_csv('cleaned2/'+filename, index=False)
