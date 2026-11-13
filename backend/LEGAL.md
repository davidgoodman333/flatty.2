# Is Flatty allowed to scrape these sites?

Checked on 30 October 2026. This is the team's own assessment for the SAI2 prototype, not legal advice. Before a public or paid launch, have it reviewed (for example by the University of Bern legal service).

## Short answer

| Source | robots.txt | Terms of use | Flatty's decision |
|---|---|---|---|
| **Flatfox** | Allows `/` for every bot. Only `/admin/`, `/partner/` and similar are blocked. | [AGB §4.2](https://flatfox.ch/c/de/agb/): reuse of published listings is reserved to the advertiser and Flatfox. No explicit ban on automated access. | **Enabled for the prototype**, through the public JSON API at a low request rate. Flatty stores facts only, links back and doesn't republish. **Ask Flatfox for written permission before launch.** |
| **Homegate** (SMG) | Partly allowed. Many query parameters are blocked. | [SMG AGB §7](https://www.homegate.ch/c/de/ueber-uns/rechtliches/agb): "Verboten ist es insbesondere, die auf den Marktplätzen zugänglichen Inhalte systematisch auszulesen (z.B. durch Scraping)". §15b lets SMG act against "unzulässiges Crawling". | **Disabled.** Pasted links aren't opened either. Users paste the listing text instead. |
| **ImmoScout24** (SMG) | Partly allowed. | Same SMG terms as Homegate. | **Disabled.** Same as Homegate. |
| **WG-Zimmer** | Listings aren't blocked. | [AGB §8](https://www.wgzimmer.ch/wgzimmer/agb.html): "Dritte dürfen Inserate oder Teile von wgzimmer.ch ohne unsere Zustimmung nicht übernehmen, auch nicht automatisiert." | **Disabled** until WG-Zimmer gives written consent. |
| **Uni Bern Welcome Center housing board** | Allows the accommodation pages. | [Legal notice](https://www.unibe.ch/legal_notice/index_eng.html): copying is allowed "for personal, academic and non-commercial use". Commercial use, and storing the content on other servers or feeding it into online services, needs prior written consent. | **Enabled for the local, academic, non-commercial prototype.** Hosts' names, e-mails, phone numbers and street addresses are cut off before saving. **Ask the Welcome Center for written consent before any hosted or public version** (it is also on the interview list as "housing office"). |
| **studentlodge.ch** (non-profit, formerly VBSL) | Allows all bots except a list of SEO crawlers. | [AGB](https://www.studentlodge.ch/AGB-315) only cover tenancy. No restriction on using the website. | **Enabled.** One request per run. |
| **HousingAnywhere** | Mostly allowed. | [Terms §5.9](https://housinganywhere.com/terms) forbid "web spiders, crawlers, or similar tools". §8.7.2 forbids automated collection. | **Disabled.** |
| **newhome** | Listings not blocked. | Couldn't be read: the site answers bots with HTTP 403. | **Disabled.** Flatty never works around bot blocking. |
| **students.ch** | Listings not blocked. | Pages sit behind an automatic bot check. | **Disabled**, for the same reason. |
| comparis, anibis, tutti | anibis and tutti block many bots. | Not yet reviewed. anibis and tutti belong to SMG, like Homegate. | **Not collected.** A user-pasted link to such a site is fetched once, only if robots.txt allows it, and isn't stored. |

### Photos

Flatty shows photos from Flatfox and studentlodge by **linking to the image files on the original site**. The student's browser loads them from flatfox.ch or studentlodge.ch. Flatty never downloads, stores or re-hosts them, each photo is credited, and the original listing is linked. Photos are copyrighted, usually by the advertiser, and Flatfox holds a licence (AGB §4.1). Linking is acceptable for this non-public prototype. Before launch it must be part of the permission requested from Flatfox. The Uni Bern board only has photos in PDFs, which Flatty doesn't open.

robots.txt alone doesn't decide the question. Homegate and WG-Zimmer allow bots in robots.txt but forbid scraping in their terms. Flatty follows the stricter of the two.

## Swiss legal background

1. **Unfair competition (UWG Art. 5 lit. c).** It is unfair to take over someone else's market-ready work product "by technical reproduction processes, without reasonable own effort". The Federal Supreme Court applied this to scraped property listings in [4C.336/2004](https://servat.unibe.ch/dfr/bger/2005/050204_4C-336-2004.html) (BGE 131 III 384, 2005). It found no violation because the scraper had invested substantial effort of its own. Flatty processes the data (risk model, fit model, matching) and doesn't copy listings 1:1. That supports Flatty's position, but it is no licence to mirror a competitor's database.
2. **Copyright (URG).** Listing texts and photos can be protected works. Flatty therefore doesn't show or re-host descriptions or images. It shows facts (rent, rooms, m², area) and links to the original listing. Switzerland has no separate database right like the EU's.
3. **Contract (terms of use).** Terms bind users who accepted them, for example when registering. A purely browsing bot is a grey area in Swiss law. The team doesn't rely on that grey area: where terms forbid scraping, Flatty doesn't scrape.
4. **Criminal law (StGB Art. 143bis, unauthorised access to a data system).** This only applies if protection is circumvented. Flatty never logs in, never bypasses captchas or bot protection (Flatfox uses DataDome) and stops on HTTP 401/403.
5. **Data protection (revDSG, in force since 1 September 2023).** Listings can contain personal data (landlord names, phone numbers, addresses). Flatty follows proportionality and purpose limitation:
   - It doesn't store contact persons, phone numbers, e-mails or images. Agency company names and the public address are kept.
   - Listings that haven't been seen for 14 days are deleted automatically (`FLATTY_RETENTION_DAYS`).
   - The student's profile isn't stored on the server. It is sent with each request to the back-end on the student's own machine.

## What the code enforces

- `app/scraper/sources.py` is the single place where each source is enabled or disabled, with the reason.
- `app/scraper/compliance.py` and `app/scraper/robots.py`:
  - check robots.txt before every request (RFC 9309, including `*` and `$` wildcards);
  - send an honest user agent (`FlattyBot/0.1`) with a contact (set `FLATTY_CONTACT`);
  - wait at least 2 seconds between requests, with a hard cap of 40 requests per run;
  - honour `Retry-After` on 429 and stop on 401/403.
- Request budgets per run: Flatfox 60, Uni Bern 90, studentlodge 5.
- Automatic refresh: at most once every 24 hours per source (a failed run is retried after 3 hours at the earliest). When a student opens a listing, Flatty checks it at the source with **one request, at most once an hour per listing**. All of this shares one rate limit per site (one request every 2 s) and a robots.txt cache renewed daily.
- Listings that a source has taken offline are hidden right away and deleted after 14 days. Flatty doesn't keep data about rented-out flats.
- A full run currently needs about 65 requests in total (Flatfox about 16 for about 730 listings, Uni Bern 48 for 42 listings, studentlodge 1 for 24 offers). It takes about 2.5 minutes.

## To do before going public

- [ ] Ask Flatfox for written permission, or a partner API agreement, for public and commercial use. The pitch's premium tier and university licence are commercial.
- [ ] Ask SMG (Homegate, ImmoScout24) about a licensed feed or partner interface.
- [ ] Ask WG-Zimmer for consent.
- [ ] Ask the Uni Bern Welcome Center for written consent for any hosted or public version.
- [ ] Review the terms of newhome, comparis, students.ch and university housing boards before adding them.
- [ ] Publish a privacy notice for students.
- [ ] Set `FLATTY_CONTACT` to a real team e-mail address.
