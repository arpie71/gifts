from collections import Counter, defaultdict
import numpy as np
from tqdm import tqdm
import wikipedia
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from googlesearch import search
import pandas as pd
import os

endpoint_url = "https://query.wikidata.org/sparql"
def get_results(endpoint_url, query):
    from SPARQLWrapper import SPARQLWrapper, JSON, POST
    sparql = SPARQLWrapper(endpoint_url, agent='Mia Test agent')
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setMethod(POST)
    return sparql.query().convert()

def parsewiki(wfield, result):
    rfield = ''
    datafield = wfield
    if datafield in result:
        w = result[datafield]  # w is a dictionary
        if ((w["type"]=="uri") | (w["type"]=="literal")):
            url = str(w["value"]).replace("http://www.wikidata.org/entity/","")
            rfield=url
    return rfield

def getPersIDs(entity):
    endpoint_url = "https://query.wikidata.org/sparql"
    wikilist = []
    query = """
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?sitelinks
     WHERE {
        ?item wdt:P31 wd:Q5.
     ?item ?label \"%s\" @en.
    ?item wikibase:sitelinks ?sitelinks.
     SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
     }
      """ % entity.title()
    results = get_results(endpoint_url, query)
    count = 0
    if((len(results["results"]["bindings"])==0)|(len(results["results"]["bindings"])>10)):
        wikilist=""
    else:
        for result in results["results"]["bindings"]:
            # Keeping track of result count
            count += 1
            if count>=1:
                wiki = parsewiki("item", result)                
                fname = parsewiki("itemLabel", result)
                descr = parsewiki("itemDescription", result)
                sitelinks = parsewiki("sitelinks", result)
                wikilist.append([entity, wiki, fname, descr,sitelinks,"s"])
    return wikilist

def search_pers(pl):
	newpers=[]
	nopers = []
	with tqdm(total=len(pl)) as pbar:
		with ProcessPoolExecutor(max_workers=25):
			for n in pl: 
				if n!="":
					pbar.update(1)
					try:
						wid = getPersIDs(n)
						newpers.extend(wid)
					except:
						print(n)
						wid=[]
						nopers.append(n)
	df=pd.DataFrame(newpers, columns=['entity','wiki','wikiname','descr','search','id'])
	return df

files = os.listdir('cleaned2')
recipdb = []
giverdb = []

# There are some recipients and givers we do not need to search for.
# For recipients, this includes "An Agency Employee"
# For givers, this includes "5 U.S.C. 7342(f)(4)"
# But we should keep these values in the data
# creating recip_name_clean and giver_name_clean columns

for newfile in files:
	df = pd.read_csv('cleaned2/'+newfile)
	df_recip = df[(df['recip_wiki'].isna())&(df.recip_name!='An Agency Employee')&(df.recip_name!='Unknown')]
	dbpers = df_recip['recip_name'].values.tolist()
	recipdb.extend(dbpers)
	df_giver = df[(df['giver_wiki'].isna())&(df.giver_name!='5 U.S.C. 7342(f)(4)')&(df.giver_name!='Foreign Government Official')&(df.giver_name!='Unknown')]
	dbpers2 = df_giver['giver_name'].values.tolist()
	giverdb.extend(dbpers2)

l = Counter(recipdb)
#print(l)
recipdf = search_pers(l)
recipdf.to_csv('scratch/recipwiki_tock.csv', index=False)
	
l2 = Counter(giverdb)
#print(l2)
giverdf = search_pers(l2)	
giverdf.to_csv('scratch/giverwiki_tock.csv', index=False)
