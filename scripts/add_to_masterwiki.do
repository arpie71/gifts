
cd \\wsl.localhost\Ubuntu\home\arpie\gifts\

import delimited using files/recips_checked.csv, clear varnames(1) encoding("utf8") bindquote(strict)

drop wikidataid 
tempfile a 
save `a'

import delimited using files/masterwiki.csv , clear bindquote(strict) varnames(1) encoding("utf8")
duplicates drop * , force
preserve
keep if wikiname==""

gen id = _n
joinby wiki using `a' , _merge(_merge) update replace

duplicates drop id , force

tempfile additions
save `additions'

restore
drop if wikiname==""

append using `additions' 
replace entity = recip if entity!=recip & recip!=""
drop id-recip_name
duplicates drop * , force
compress

export delimited using files/masterwiki_new.csv, replace 

