Readme file for the gifts data

# Getting gifts data

There is not a dedicated webpage for the gifts data. Instead, it is available at:
https://www.federalregister.gov. Do a search for "office of the chief protocol gifts" and the relevant documents will be returned.

I have the code set up to parse xml files. The xml data is under "Other formats". Copy the url and paste it into gifts_urls_xml.txt.
The data are about two years behind. In February 2024, the gifts data for 2022 were just released. So the data will have to be updated only once a year.


# Running the script
The Python script is called **`download_data.py.`** The url for the xml data and the year that the gifts were given are necessary. 
The script will scrape the data and save the output to a csv file in the raw directory. The data in this file have not been parsed.

There is also a urls.csv file in the files subdirectory. If you want to get really fancy, you can run the following bash lines to scrape all the Federal Register urls that we have:

```
while IFS="," read -r rec_column1 rec_column2 
do
  python download_data.py --url $rec_column1 --year $rec_column2
done < <(tail -n +1 files/urls.csv | tr -d '\r')
```

This should be run rarely. If the file is updated subsequently, it's enough to run:
`python download_data.py --url 'URL' --year YEAR`

Here is an example of running the script on 2022 data (released in 2024):
`python download_data.py --url 'https://www.federalregister.gov/documents/full_text/xml/2024/02/15/2024-03129.xml' --year 2022`


### Parsing the data
Parsing the raw data will proceed in two steps. The first step is to split the individual fields into their components.
The field `item` for instance has a description of the item, the date received, the estimated value, and the disposition in it.

There will have to be some manual checking of the data. The scripts will not be able to foresee every eventuality. 

The Python script **`parseandclean.py`** will parse the columns and save the data into the cleaned folder.

Once we have those columns parsed, we should do a Wikidata search for the givers and recipients. A quick check of the results suggests that this process should not be fully automated.
For example, Wikidata returns two possibilities for "Pierre Mattei" and 5 possibilities for "Qin Gang".
Some names will be consistent over time--e.g., US Presidents and Vice Presidents--so one possibility would be to have a standard names file that would fill in those Wikidata IDs earlier.
 
The script **`wikifind.py`** will do a SparQL search for recipients and givers. It will return all matching values so the file will have to be checked manually.
The goal is to have a masterwiki file that could serve as a lookup so we will not have to run the SparQL query with each update.
 
 
## Next steps
There are a couple of things that could improve the process
- Add a list of recipients and givers without Wikidata IDs