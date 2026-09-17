from collections import Counter, defaultdict
import numpy as np
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
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


if not os.path.isdir('scratch'):
    os.mkdir('scratch')

df = pd.read_csv('files/givernames_tock.csv')
dbpers2 = df['giver_name'].values.tolist()

l2 = Counter(dbpers2)
#print(l2)
giverdf = search_pers(l2)	
giverdf.to_csv('scratch/giverwiki_tock.csv', index=False)
