cd \\wsl.localhost\Ubuntu\home\arpie\gifts\cleaned

local files: dir "" files "*"

local i = 1
foreach file of local files {
    import delimited using `file', clear bindq(strict) maxquotedrow(10000) stringcol(_all) encoding("utf-8")
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