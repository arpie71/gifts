cd \\wsl.localhost\Ubuntu\home\arpie\gifts\cleaned

local files: dir "" files "*"

local i = 1
foreach file of local files {
    import delimited using `file', clear bindq(strict) maxquotedrow(10000) stringcol(_all) encoding("utf-8")
	duplicates drop * , force
	compress
	if `i'==1 {
	    save ../giftsnew.dta , replace
	}
	if `i'>1 {
		append using ../giftsnew.dta
		save ../giftsnew.dta , replace

	}
	local i = `i'+1
}


generate dollar_count = length(item_orig) - length(subinstr(item_orig, "$", "", .))

replace estval = ustrregexs(1) if dollar_count==1 & estval=="" & ustrregexm(item_orig,"\\$(\d+,?\d+(\.00)?)")

destring estval, gen(estval_num) force ign("$, ")
replace estval_num = .a if (estval=="Unknown"|ustrregexm(estval,"\$Unknown")) & estval_num==.
replace estval_num = .b if ustrregexm(estval,"$not submitted") & estval_num==.
replace estval_num = .c if ustrregexm(estval,"over|above|more than",1) & estval_num==.
replace estval_num = .c if ustrregexm(item_orig,"over minimum value",1) & estval_num==.



*******************
** FIXING DATES
*******************

replace recd = "October 23, 2000" if recd=="October 23, 200"

gen date = date(recd,"MDY",2050)
gen date2 = date(recd,"DMY",2050)

replace date = date2 if date==. & date2~=. 
gen yearnum = float(year(date))
format date %td
replace date = .a if recd=="Unknown" | recd=="unknown"
replace yearnum = .d if recd=="Unknown" | recd=="unknown"

gen daterange = ustrregexm(recd,"-")
replace daterange=0 if date2~=. 
*bro recd yearnum daterange recd_std if daterange==1

gen year2 = ustrregexs(0) if ustrregexm(recd,"[12]\d{3}") & yearnum==.
destring year2, replace


*******************
** Disposition & Location
** One or the other should be filled in, not both
*******************

replace disposition="" if disposition~="" & location~=""
replace disposition = ustrregexs(0) if ustrregexm(item_orig,"Transferred to GSA|Archives Foreign|Sent to GSA for disposition|Reported to GSA|Government property") & disposition=="" & location=="" 
replace disposition = "N/A" if ustrregexm(item_orig,"^Travel|^Gift of Travel|^Transport?at?ion|Lodging and meals|^Ground transportation|^Air travel|^Food, lodging|^Round trip|^Bus transportation|^Air transportation",1) & disposition==""
replace location = "N/A" if ustrregexm(item_orig,"^Travel|^Gift of Travel|^Transport?ati?on|Lodging and meals|^Ground transportation|^Air travel|^Food, lodging|^Round trip|^Bus transportation|^Air transportation",1) & location==""

replace disposition = "N/A" if ustrregexm(item_orig,"^lodging|^hotel|^meals|^accomm?odation|^expended for|^airfare|^\d+ nights?|^helicopter|^in-kind lodging|^august",1) & disposition==""
replace location = "N/A" if ustrregexm(item_orig,"^lodging|^hotel|^meals|^accomm?odation|^expended for|^airfare|^\d+ nights?|^helicopter|^in-kind lodging|^august",1) & location==""


*******************
** Travel gifts
*******************

gen travel = (ustrregexm(item_orig,"^Travel|^Gift of Travel|^Transport?at?ion|Lodging and meals|^Ground transportation|^Air travel|^Food, lodging|^Round trip|^Bus transportation|^Air transportation",1))
replace travel = 1 if ustrregexm(item_orig,"^lodging|^hotel|^meals|^accomm?odation|^expended for|^airfare|^\d+ nights?|^helicopter|^in-kind lodging",1)

*******************
** REASON
** At least some of the missing reasons are because of multiple gifts that get separated in parsing
** Filling those in manually
*******************

destring unnamed0 , replace
sort year unnamed0

gen reason_orig = reason

preserve
keep unnamed0-estval 
export excel using ../files/reasons_fillin.xlsx , replace firstrow(var)
restore




/*
preserve
keep if recip_wiki==""
duplicates drop recip_name, force
keep recip recip_name recip_wiki 
export delimited using ../files/recipnames_tock.csv , replace  
restore

/*
preserve
keep if giver_wiki==""
duplicates  drop giver_name, force
keep giver giver_name giver_wiki
export delimited using ../files/givernames_tock.csv, replace  
restore