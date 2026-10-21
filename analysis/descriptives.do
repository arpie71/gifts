* Descriptive statistics for the foreign gifts data, Stata version.
* Reads the analysis file built by analysis/build_analysis_data.py.
* Run from the repo root: do analysis/descriptives.do

import delimited using analysis/output/gifts_analysis.csv, clear bindquote(strict) ///
	maxquotedrows(10000) encoding("utf-8") varnames(1)

*******************
** Gifts by year and branch of the reporting agency
*******************
tab year
tab branch
tab year branch

*******************
** Individuals: top recipients and givers (Wikidata-linked only)
*******************
preserve
keep if recip_has_qid==1
collapse (count) gifts=year (sum) value=estval_num (min) first=year (max) last=year ///
	(firstnm) name=recip_wikiname, by(recip_wiki)
gsort -gifts
list name recip_wiki gifts value first last in 1/20, noobs sep(0)
restore

preserve
keep if giver_has_qid==1
collapse (count) gifts=year (sum) value=estval_num (firstnm) name=giver_wikiname country=giver_country, by(giver_wiki)
gsort -gifts
list name country giver_wiki gifts value in 1/20, noobs sep(0)
restore

*******************
** Countries: totals, and a balanced country-year panel
*******************
preserve
drop if giver_country==""
collapse (count) gifts=year (sum) value=estval_num, by(giver_country giver_iso3)
gsort -gifts
list in 1/25, noobs sep(0)
restore

preserve
drop if giver_iso3==""
gen one = 1
collapse (sum) gifts=one value=estval_num, by(giver_iso3 year)
encode giver_iso3, gen(cid)
xtset cid year
tsfill, full
replace gifts = 0 if gifts==.
gen any_gift = gifts>0
* Share of country-years with any recorded contact, by year
tabstat any_gift, by(year) stat(mean)
restore

*******************
** Giver type by recipient branch (row percentages)
*******************
tab branch giver_role, row nofreq

*******************
** Office vs officeholder: people seen under more than one branch
*******************
preserve
keep if recip_has_qid==1
* earliest receipt year under each branch
bysort recip_wiki branch (recd_year): keep if _n==1
bysort recip_wiki: gen n_branch = _N
keep if n_branch>1
sort recip_wiki recd_year
list recip_wikiname branch recd_year if n_branch>1, noobs sepby(recip_wiki)
restore
