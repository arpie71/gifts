# Empirical memo: careers, revolving doors, and institutional influence in the foreign-gifts data

*Revised analysis, 2026-11-05. Every number below comes from `output/numbers.json` and `output/tables/`
(rebuilt by `run_all.sh`). Tables are cited by file name.*

## Bottom line

1. **The data support a descriptive, theory-building paper, not causal claims.** No design isolates
   variation in careers or personnel that is unrelated to what the office does. Below, every result is
   labeled by the kind of comparison it makes.
2. **Position dominates career.** Interaction counts track the formal office (cabinet-level offices
   above all), not career length, prior mobility, or accumulated history. That holds between people and
   within the same person.
3. **Organizations keep their foreign ties when the people who carried them leave.** At the tie level,
   other personnel continue a country relationship at the same rate whether or not the original carriers
   stay. Ties follow the office more than the person, with a modest, imprecise person-carried component.
4. **Brokerage is concentrated and positional.** Its association with career mobility mostly disappears
   against degree-preserving null graphs. Below cabinet level, brokers are military service chiefs,
   protocol officers, and senior senators on foreign-affairs committees.
5. **Revolving-door claims (government to private sector and back) cannot be tested.** The gift record
   observes only public-sector legs of careers. Wikidata records 25 moves into the private sector among
   all linked recipients, and staff careers are mostly undocumented.

## 1. What the data can and cannot observe

**Linkage** (`tab_audit_status`, `tab_audit_by_group`, `tab_audit_checks`, `fig_linkage`).
* 71.0% of gift records have a recipient linked to a human Wikidata item. For givers the figure is 65.7%.
  The original paper's 76% giver figure counts the 1,108 records linked to states, ministries, IOs, and 8
  link errors (Wikimedia categories, a flag design) as linked.
* **Missingness is not random.** Recipient linkage is 84% for White House records and 35% for
  intelligence. Giver linkage is 96% for heads of state and 22% for "Other/unknown" givers, and 0.5% for
  intelligence, where the giver is withheld. Linkage also falls after 2008 (`fig_linkage`). Any
  person-level result is therefore weighted toward visible offices and visible givers.
* **Career information is thinner still, and most selective for the people the theory cares about.**
  58% of linked recipients (593 of 1,022) have at least one dated Wikidata spell. The rates are 93% for
  cabinet-level officials, 84% for legislators, and **36% for agency, military, and diplomatic staff**
  (`tab_career_desc`). Staff careers recorded in Wikidata typically begin with the post in which the
  person is observed (median recorded career at first gift: 1 year), so earlier careers are unobserved. Among recipients with career data, 18.6% of their gift-years fall in years when
  Wikidata records no U.S. public position, so even documented careers are incomplete.
* **Identifier problems found and handled:**
  * Two heavily observed people had no claims at all: George W. Bush (888 records) and Laura Bush (445).
    Their QIDs come from the bare-office rule ("President" → holder by year, 1,614 records in total),
    which `scripts/wiki_properties.py` never enriches. This is now supplemented.
  * 23 links have impossible dates, e.g. a recipient in 2018 linked to a Minnesota state senator who
    died in 1933.
  * 1 lookup key maps to two QIDs, and 34 duplicate key rows were already dropped by the parser.
  * 7 recipient and 67 giver QIDs carry name variants with no token in common: name changes,
    transliterations, or mislinks.
  * 1 recipient and 3 giver names are linked to different QIDs.
  * Spot checks while building the prominence groups found two further likely mislinks that the date
    rules cannot catch: "Michelle Hawes, Spouse" is linked to the actress Keeley Hawes, and "Barbara
    Jones, Wife of the Ambassador … to Iraq" is linked to an item labeled Barbara S. Jones. Hand
    review of the remaining name variants will probably find more.
  * Item-level lists are in `data/audit_*.csv`. They should be reviewed by hand and corrected in
    `files/masterwiki_new.csv`, not in this analysis.

**Risk set.** A person is observed in the gift data only while holding an office that receives
reportable gifts. Count models use years in a dated U.S. public position (from Wikidata) plus any gift
year, so zeros are meaningful. That is possible only for the 58% with dated careers.

## 2. Claim by claim

Prominence groups (`tab_career_desc`), from 1,015 linked recipients in the panel years:
* cabinet level and above (170);
* family of presidents, vice presidents, and cabinet officials (13);
* legislators (264, including spouses whose gifts Congress reports);
* agency, military, and diplomatic staff (568).

Evidence types: **B** = difference between people; **W** = change within the same person after a
transition; **O** = change within an organization after turnover; **N** = persistence or transformation
of a network; **X** = cross-sectional association only.

### Career duration: do longer careers or more appearances mean more extensive networks?
*Verdict: not supported. Descriptive only.*
* Between people (B; `tab_main_career`, col. 1), career length is unrelated to gifts: 0.023 (SE 0.093).
  Tenure in the current organization is negatively related (−0.41): interactions are concentrated early
  in a post, or in short senior posts. Holding cabinet office now multiplies gifts by about 4.3 (coef.
  1.46).
* Legislators have the longest careers (median 21 years at first gift) and the fewest gifts per active
  year (1.4, against 9.7 for cabinet officials) (`tab_career_desc`).
* Repeated appearance persists across people (B: prior gifts +0.61) but does not accumulate within a
  person (W: −0.22). The within-person sign mainly reflects regression to the mean and the known bias of
  lagged outcomes in fixed-effects models. It is not evidence of decay.
* Without cabinet-level officials, the tenure association vanishes (`tab_robust_samples`).

### Career mobility: do movers occupy more central or bridging positions?
*Verdict: not supported once degree is held fixed (X, B, W).*
* With the number of countries controlled, prior cross-sector moves, prior organizations, and having
  served under several agencies are unrelated to participation coefficients, betweenness, or bridging
  communities between people (`tab_brokerage`). One within-person coefficient is significant at 5%
  (betweenness +3.1 per move) among ten estimated, so treat it as fragile.
* **Permutation test** (`tab_permutation`, `fig_permutation`): the correlation between betweenness and
  prior moves lies inside the degree-preserving null in 6 of 7 administrations. Obama I is the exception
  (ρ = 0.12, null mean 0.08, p < 0.005). A label permutation of mobility across people gives p = 0.40.
  The apparent mobility–brokerage link is mostly a degree effect.

### Revolving-door pathways: do transitions raise the number, diversity, or reach of interactions?
*Verdict: positional moves do; lateral and cross-sector moves below cabinet do not, or cannot be
estimated. Public↔private moves cannot be tested.*
* Career pathways (`tab_transitions`, `fig_pathways`, `fig_career_timelines`): 883 moves between
  organizations. 46% stay within a sector, and 13% cross between public service and the private,
  academic, or IO domains. The dominant path is state legislature → Congress (138 moves).
* Stacked event study (W; `tab_event_study`, `fig_event_study`):
  * After any change of organization, gifts rise by 1.37 log points, with no pre-trend (t−3, t−2:
    0.20, SE 0.19).
  * The rise comes from **moves into cabinet-level office** (1.79, 26 events). Lateral or non-cabinet
    moves show 0.32 (SE 0.51; 78 events).
  * Moves by agency, military, and diplomatic staff show 1.45 (p < 0.05), but the pre-period
    coefficient is 0.95 (SE 0.48), so anticipation or selection cannot be ruled out.
  * Non-cabinet cross-sector moves (26 events) are followed by fewer gifts, and the year of the move is
    not identified (no gifts at all).
  * Public↔non-public moves (12 events) cannot be estimated: three event-time cells have no gifts.
* **Placebo:** 200 sets of random pseudo-moves give a mean post coefficient of −0.01 (SD 0.25), against
  an observed 1.23. The jump is not an artifact of the stacked design, but it is a change of office, not
  a career effect.
* The within-person coefficient on prior organizations (+0.56) survives every exclusion, including
  staff only (+0.57, p < 0.05; `tab_robust_samples`) and all transition definitions
  (`tab_robust_transitions`). The count of prior organizations rises only when a person moves, so this
  is the same contrast as the event study. The coefficient on cross-sector moves turns negative without
  cabinet officials (−0.75).

### Institutional memory and continuity: do organizations keep networks when personnel change?
*Verdict: supported as a descriptive regularity (O). Ties mostly stay with the organization.*
* Agency-year (O; `tab_org_continuity`): personnel turnover is unrelated to the share of last year's
  giving countries that give again (−0.015, SE 0.075). A change in the top recipient is not significant
  (−0.04, SE 0.025). Only 15 agencies contribute, so power is low. Results are the same counting
  unlinked recipients by name (col. 5).
* Tie-level, agency × country × year (O; `tab_tie_memory`):
  * When every U.S. carrier of a tie leaves the agency, the chance the tie recurs within three years
    falls from 64% to 47%.
  * The chance it recurs **through other personnel** is unchanged: 47.9% against 47.4%; coef. 0.019,
    SE 0.029, with agency-year and country-year FE.
  * What is lost is the departed person's own repeat contact. The agency's relationship continues
    through successors.
* Follow the person (`tab_movers`, 76 episodes): at their new agency, movers receive 13.9% of gifts
  from countries that gave to them before, against 9.4% for colleagues there (difference 4.5 points,
  sign-flip p = 0.11). For specific foreign individuals the shares are 3.6% and 2.5% (p = 0.65). At the
  old agency, the mover's countries account for less of colleagues' gifts after the move (9.4%, against
  12.6% before; p = 0.017). This is a modest, imprecise sign that some ties travel with people.
* Agencies connected by shared personnel (`fig_agency_network`): only 8% of linked recipients appear
  under more than one agency. The personnel network runs mostly through the White House, State,
  Defense, the CIA, and the Senate.

### Bureaucratic brokerage: who connects otherwise separate agencies, governments, or communities?
*Verdict: descriptive (X).*
* On the U.S. side (`tab_brokers_ordinary`), 94% of the top decile of brokers are cabinet level or
  above: betweenness in the recipient–agency–country graph, among people with 3+ gifts. Below cabinet
  level the brokers are:
  * Navy chiefs of naval operations (Roughead, Greenert), the Chief of Protocol (Capricia Marshall),
    and defense intelligence officials (Vickers, Stewart);
  * on the legislative side, senators on foreign-relations and armed-services committees (McConnell,
    McCain, Lugar, Frist, Graham).
* On the foreign side (`tab_brokers_foreign`), 23% of linked foreign individuals reach more than one
  U.S. agency (33% of heads of state and royalty, 20% of others). The leading intermediaries below
  head-of-state level are senior security and legal officials, e.g. Lebanon's army commander Kahwaji
  and Qatar's attorney general Al-Marri, and long-serving ambassadors such as Al Otaiba and Suleymanov.
  The original `giver_role` codes Al-Marri as "Military", one of several role misclassifications to
  check.
* Lagged betweenness predicts a lower hazard of leaving the organization (`tab_hazard`). Network
  position does not predict the next career move, except for one marginal coefficient among non-cabinet
  officials.

### Temporal change across administrations, crises, and reforms
*Verdict: supported as description (N). Confounded by reporting practice.*
* By administration (`tab_network_periods`), 55–61% of agency–country ties carry over from one
  administration to the next through Obama II. Carryover falls to 31% under Trump and 40% under Biden.
* Modularity rises from about 0.25–0.32 to 0.39–0.42, so the network becomes more segmented. The top
  10 recipients' share falls from 77% (Clinton) to 53% (Obama II) and rises again to 69% (Biden).
* Yearly (`fig_network_change`, `fig_personnel_movement`): the sharpest break is 2020. Only 9% of
  agency–country ties carry over from 2019, consistent with COVID-era travel.
* The post-2016 decline coincides with the reporting-volume decline documented in the original paper,
  so changes in reporting and in behavior cannot be separated. No reform (DHS 2003, ODNI 2005) shows a
  visible discontinuity at this resolution.

### Selection versus influence after appointment
*Verdict: partly separable, descriptively.*
* At entry (B; `tab_selection`), people with more prior cross-sector moves and longer careers receive
  more gifts in their first year (0.29 and 0.25, p < 0.05). They do not enter more central or bridging
  positions.
* The event studies (W) show that what changes after appointment is the office. The hazards show that
  prior network position does not select people into their next move.
* The theory's claim that careers shape what people do *after* appointment would need behavior or
  decisions as outcomes. The gift record does not contain them.

## 3. Robustness (`tab_robust_samples`, `tab_robust_transitions`, `tab_robust_windows`)

* **Excluding prominent people:** the top 1% and top 25 recipients are all cabinet level. Within-person
  results for prior organizations hold without cabinet officials, without the top 25, without the White
  House branch, and among agency, military, and diplomatic staff alone (175 people; +0.57). Dropping
  also the 10 most-observed staff leaves the estimate similar but no longer significant (+0.52), so
  among staff it rests on a few frequently observed people. Tenure and cross-sector associations do not
  hold.
* **Transition definitions:** any sector change, sequential spells only, public/private/academic/IO
  domain changes, and any change of organization give the same within-person signs. Domain changes are
  imprecise.
* **Network windows** (t−3..t−1, t−5..t−1, all prior years) give the same null results for brokerage
  persistence and for mobility hazards.
* **Linked-only versus all identifiable recipients:** the organizational results are unchanged
  (`tab_org_continuity`, col. 5).

## 4. What cannot be tested, and the data that would be needed

| Claim | Why not testable here | Data required |
|---|---|---|
| Post-government revolving door (lobbying, firms, think tanks) | The gift record ends when public office ends. Wikidata P108 is sparse (37.5% of recipient employers dated; 25 moves into private) | LDA lobbying disclosures and FARA registrations linked by name/QID; post-service employment from financial disclosures (OGE 278); LegiStorm for congressional staff |
| Careers of ordinary staff | 64% of staff recipients have no dated Wikidata career, and those who do were documented because they became prominent | Federal personnel records (OPM workforce data; restricted-use CPDF for named careers); State Department chief-of-mission lists; military officer biographies |
| International organization and research careers | 12 IO spells among recipients | IO staff directories; CVs; ORCID for researchers |
| Generic positions ("member", "board member") | The claims snapshot drops the P642/P2937 qualifiers that name the organization | Re-download claims with qualifiers |
| Ideas and practices that travel; adaptability; policy influence | No outcome measures of behavior or decisions | Policy documents, voting, statements, agreements, linked by agency and date |
| Intelligence networks | The giver is withheld in 99% of intelligence records | None available publicly |
| Causal effects of careers or turnover | Appointments and moves are not as-if random | Rotation schedules with fixed terms (military commands, ambassadorial rotations) as quasi-random timing; deaths or unexpected resignations as turnover shocks |

## 5. Implications for the paper

* Frame the career analysis as **descriptive and theory-building**. The strongest relational results are
  institutional continuity of ties after personnel exit (O) and the concentration of brokerage in
  positions (X, N). The career-mobility hypotheses are not supported in these data, and the paper
  should say so.
* The "office versus officeholder" section can cite the tie-level result directly: departures cut the
  departed person's own repeat contact, not the agency's relationship.
* Report the linkage and career-coverage limits (above) alongside any person-level result, and avoid
  generalizing from cabinet-level officials to staff.
* Suggested upstream fixes in the original pipeline (not made here):
  * enrich the `ROLES` QIDs in `scripts/wiki_properties.py`;
  * review `data/audit_implausible_links.csv` and `audit_name_variants.csv`;
  * decide whether non-person giver QIDs should be counted as "linked" in the paper's coverage numbers.
