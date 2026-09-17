
from SPARQLWrapper import SPARQLWrapper, JSON, POST

import pandas as pd
import os

os.chdir('gifts/files/')

def get_results(endpoint_url, query):
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



def ent_search_many(wiki_ids):
	endpoint_url = "https://query.wikidata.org/sparql"
	values = " ".join(f"wd:{wid}" for wid in wiki_ids)
	wikilist = []
	query = f"""
	SELECT DISTINCT ?item ?itemLabel ?itemDescription
	WHERE {{
		VALUES ?item {{ {values} }}
		?item wdt:P31 ?type .
		SERVICE wikibase:label {{
			bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en".
		}}
	}}
	"""
	results = get_results(endpoint_url, query)
	for result in results["results"]["bindings"]:
		wiki = parsewiki("item", result)                
		iteml = parsewiki("itemLabel", result)                
		wdesc = parsewiki("itemDescription", result)
		wikilist.append([wiki, iteml, wdesc,])
	return wikilist



df = pd.read_excel('gifts_new_adds_staging.xlsx')
wiki = df.loc[df.WikidataID.str.startswith("Q"), "WikidataID"].unique().tolist()


from itertools import batched
results = []

for batch in batched(wiki, 200):
    results.extend(ent_search_many(batch))

dfnew = pd.DataFrame(results, columns=['wiki','wikiname','descr'])

dffinal = df.merge(dfnew,left_on='WikidataID', right_on='wiki')
dffinal.to_csv('masterwiki2.csv',index=False)



import pandas as pd
import os

os.chdir('gifts/files/')

df = pd.read_excel('gifts_new_adds_staging.xlsx')
nilwiki = df.loc[df.WikidataID=='NIL', "giver_name"]

nilwiki.to_csv(
    "nowiki2.txt",
    mode="a",
    index=False,
    header=False
)