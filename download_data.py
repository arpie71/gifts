description = """Script to download gifts data from the federal register"""
import argparse
from argparse import RawTextHelpFormatter

def cli():
    parser = argparse.ArgumentParser(description=description, formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "--url",
        required=True,
        type=str,
        default='',
        help="XML url to scrape")
    parser.add_argument(
        "--year",
        required=True,
        type=str,
        default='',
        help="Year of data (to save raw data)")
    args = parser.parse_args()
    url = args.url
    year = args.year
    return (url, year)

def get_year(url):
    from bs4 import BeautifulSoup
    import pandas as pd
    import requests
    import time
    import re
    t =  requests.get(url)
    t.encoding = t.apparent_encoding
    soup = BeautifulSoup(t.text, features="html.parser")
    g= soup.findAll('row')
    title = soup.find('subject').text
    s = re.search('(Calendar Year )(.+)', title)
    yr = s.group(2)
    gifts = []
    for i in g:
        r=i.findAll('ent')
        if len(r)==4:
            gifts.append((yr,r[0].text,r[1].text,r[2].text,r[3].text))
        elif len(r)==3:
            gifts.append((yr,r[0].text,r[1].text,r[2].text,""))
        elif len(r)==2:
            gifts.append((yr,r[0].text,r[1].text,"",""))
        else:
            print(r)
    return gifts
    print(url, " is done")

def main(url, year):
    from bs4 import BeautifulSoup
    import pandas as pd
    import requests
    import time
    import re
    import os

    if not os.path.isdir('raw'):
        os.mkdir('raw')
    gift = get_year(url)
    print("Done scraping xml data")
    df = pd.DataFrame(gift, columns=['year','recip','item','giver','reason'])
    df.to_csv('raw/gifts'+str(year)+'.csv')
    print("Saved file raw/gifts"+str(year)+".csv")

if __name__=='__main__':
    url, year = cli()
    main(url,year)
