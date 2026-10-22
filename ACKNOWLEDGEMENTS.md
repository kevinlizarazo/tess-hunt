# Acknowledgements

Any publication or data release built on this project's results must carry these acknowledgements and cite the
products it used, with the sector ranges.

## TESS

This paper includes data collected with the TESS mission, obtained from the MAST data archive at the Space
Telescope Science Institute (STScI). Funding for US Institutions for the TESS mission is provided by the NASA
Explorer Program. STScI is operated by the Association of Universities for Research in Astronomy, Inc., under NASA
contract NAS5–26555.

| Product | DOI | Also cite |
|---|---|---|
| SPOC 2-min light curves | 10.17909/t9-nmc8-f686 | Jenkins et al. 2016 |
| SPOC target pixel files | 10.17909/t9-yk4w-zc73 | Jenkins et al. 2016 |
| SPOC DV reports (single, multi-sector) | 10.17909/t9-2tc5-a751, 10.17909/t9-yjj5-4t42 | Jenkins et al. 2016 |
| TESS-SPOC FFI light curves (CC BY 4.0) | 10.17909/t9-wpz1-8s54 | Caldwell et al. 2020 |
| QLP light curves (CC BY 4.0) | 10.17909/t9-r086-e880 | Huang et al. 2020a, 2020b; Kunimoto et al. 2021, 2022 |
| Calibrated FFIs (pixel vetting, through TESScut) | 10.17909/0cp4-2j79 | Brasseur et al. 2019 |

QLP asks users of Sector 27 and later data to consider offering a QLP team member co-authorship (invited, not
required).

Light curves that the public bucket lacks come from MAST's download API
(https://mast.stsci.edu/api/v0.1/Download/file); the TESS acknowledgement above, MAST's text for TESS data, covers
them.

The novelty check reads SPOC's TCE statistics tables from MAST's TCE bulk downloads page
(https://archive.stsci.edu/tess/bulk_downloads/bulk_downloads_tce.html), which gives no DOI or citation for them.
They are outputs of SPOC's data validation, whose DOIs and citation are in the table above.

## TESS Input Catalog

The sample cut, the known-planet host filter and the density check use stellar parameters from the TESS Input
Catalog v8.2 (TIC), queried through MAST. MAST's TIC v8.2 release notes name its papers: Stassun et al. 2019 (AJ 158,
138) for version 8, and Paegert et al. 2021 (arXiv:2108.04778) for versions 8.1 and 8.2. Cite both.

## Gaia

This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia),
processed by the Gaia Data Processing and Analysis Consortium (DPAC,
https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions,
in particular the institutions participating in the Gaia Multilateral Agreement.

Gaia DR3's credit and citation instructions
(https://gea.esac.esa.int/archive/documentation/GDR3/Miscellaneous/sec_credit_and_citation_instructions/) ask users
of Gaia DR3 data to cite both the Gaia mission paper and the Gaia DR3 release paper:

- Gaia Collaboration, Prusti, T., et al. 2016, The Gaia mission (A&A 595, A1)
- Gaia Collaboration, Vallenari, A., et al. 2023, Gaia Data Release 3: Summary of the contents and survey properties
  (doi:10.1051/0004-6361/202243940)

and, as appropriate, the papers that describe the data used. The dwarf cut uses FLAME masses and radii from
`gaiadr3.astrophysical_parameters`, and the novelty check uses `gaiadr3.vari_eclipsing_binary`. From Gaia's list of
DR3 papers (https://www.cosmos.esa.int/web/gaia/dr3-papers):

- Creevey et al., Gaia Data Release 3: Astrophysical parameters inference system (Apsis) I - Methods and content
  overview (arXiv:2206.05864)
- Mowlavi et al. 2023, Gaia Data Release 3: The first catalogue of Gaia eclipsing binaries - Candidate identification
  (A&A 674, A16)

The triage tables publish each star's RUWE, and the vetting records publish RUWE and Gaia DR3 positions and proper
motions, all from Gaia's astrometric solution. The credit page lists the paper on that solution among those
describing Gaia EDR3, the early instalment of DR3:

- Lindegren, L., Klioner, S., Hernández, J., et al. 2021b, Gaia Early Data Release 3. The astrometric solution
  (A&A 649, A2; doi:10.1051/0004-6361/202039709)

The vetting records' neighbour tables (`neighbours.csv`) also publish Gaia G magnitudes and BP-RP colours. Gaia's
list of EDR3 papers (https://www.cosmos.esa.int/web/gaia/edr3-papers) gives the paper on that photometry beside
Lindegren et al. under "Processing papers":

- Riello, M., et al. 2021, Gaia Early Data Release 3: Photometric content and validation (A&A 649, A3;
  doi:10.1051/0004-6361/202039587)

The TIC-duplicate measurement's tarball under `results/benchmarks/` holds Gaia DR2 source ids and parallaxes, which
come through the TIC. For those, cite the Gaia DR2 release paper with the mission paper above:

- Gaia Collaboration, Brown, A. G. A., et al. 2018, Gaia Data Release 2. Summary of the contents and survey
  properties (A&A 616, A1)

Gaia data are distributed under the CC BY-NC 3.0 IGO license (https://www.cosmos.esa.int/web/gaia-users/license),
with credit to "ESA/Gaia/DPAC". The `ruwe` column in the triage tables under `results/triage/`, the vetting records'
neighbour tables and the other Gaia values [results/README.md](results/README.md) lists stay under those terms, not
CC BY 4.0.

## ExoFOP

This research has made use of the Exoplanet Follow-up Observation Program (ExoFOP; DOI: 10.26134/ExoFOP5) website,
which is operated by the California Institute of Technology, under contract with the National Aeronautics and
Space Administration under the Exoplanet Exploration Program.

ExoFOP's data-use guidelines (https://exofop.ipac.caltech.edu/tess/pcp.php) treat data associated with a data
provider as that provider's property. Published data is cited to its article; unpublished data can be cited by the
contributor name and the ExoFOP URL, e.g. (Author, from exofop.ipac.caltech.edu). Any TOI or CTOI row quoted in a
dossier is credited to its ExoFOP contributor and the ExoFOP page, or to the published paper when one exists.

M3's vetting reads more from the ExoFOP website (DOI: 10.26134/ExoFOP5). The literature search reads each vetted
star's target page: its TOIs, CTOIs, comments, planet parameters and imaging rows, kept in each record's
`literature.json`. TRICERATOPS reads the machine-readable contrast curves ExoFOP holds for TIC 164767175: Gemini
'Alopeke speckle (2019-10-15), WIYN NESSI speckle (2019-01-21) and Palomar PHARO adaptive optics (2018-12-22), each
named with its ExoFOP contributor in the imaging rows of `results/vetting/164767175-1/literature.json`, with its file
and sha256 in `provenance-triceratops.json` beside it. Each curve is credited to its contributor and the ExoFOP page,
or to the published paper when one exists.

## NASA Exoplanet Archive

This research has made use of the NASA Exoplanet Archive, which is operated by the California Institute of
Technology, under contract with the National Aeronautics and Space Administration under the Exoplanet Exploration
Program.

The archive asks users to cite Christiansen et al. 2025, its paper in the Planetary Science Journal
(doi:10.3847/PSJ/ade3c2).

## CDS

The eclipsing-binary catalogs of Kostov et al. 2025 and Justesen and Albrecht 2021 are read through VizieR, and VSX
is matched to the sample through the CDS cross-match service. The texts and papers from CDS's acknowledgement page
(https://cds.unistra.fr/help/acknowledgement/):

This research has made use of the VizieR catalogue access tool, CDS, Strasbourg Astronomical Observatory, France
(DOI : 10.26093/cds/vizier).

- Ochsenbein et al. 2000, A&AS, 143, 23, "The VizieR database of astronomical catalogues."

This research has made use of the CDS cross-match service, Strasbourg Astronomical Observatory, France.

- Boch et al. 2012, ASPC, 461, 291, "The CDS Cross-Match Service"
- Pineau et al. 2020, ASPC, 522, 125, "The CDS Cross-match Service: Key Figures, Internals and Future Plans"

M3's literature search asks SIMBAD's TAP service for each vetted star's names. From the same page:

This research has made use of the SIMBAD database, CDS, Strasbourg Astronomical Observatory, France.

- Wenger et al. 2000, A&AS, 143, 9, "The SIMBAD astronomical database"

VizieR's rules of usage (https://cds.unistra.fr/vizier-org/licences_vizier.html) ask that each catalogue's authors,
producer and publisher be cited; the catalogues are cited below.

## Eclipsing-binary catalogs

The null threshold drops, and the novelty check fails, signals that match a catalogued eclipsing binary.

- TESS-EBs at MAST (https://archive.stsci.edu/hlsp/tess-ebs), CC BY 4.0, DOI 10.17909/t9-9gm4-fx30. Its page asks
  users to "cite the appropriate paper(s) below and the DOI": Prša et al. 2022, TESS Eclipsing Binary Stars. I.
  Short-cadence Observations of 4584 Eclipsing Binaries in Sectors 1-26 (ApJS 258, 16).
- Kostov V.B., Powell B.P., et al. 2025, The TESS Ten Thousand Catalog: 10,001 uniformly vetted and validated
  eclipsing binary stars detected in Full-Frame Image data by Machine Learning and analyzed by citizen scientists,
  ApJS 279, 50 (VizieR J/ApJS/279/50, tables 3 and 4).
- Justesen A.B., Albrecht S. 2021, Temperature and distance dependence of tidal circularization in close binaries: a
  catalog of eclipsing binaries in the southern hemisphere observed by the TESS satellite, ApJ 912, 123 (VizieR
  J/ApJ/912/123, table 2).
- VSX, the AAVSO International Variable Star Index (VizieR B/vsx): Watson C., Henden A.A., Price A. 2006
  (2006SASS...25...47W). VSX's acknowledgments page (https://www.aavso.org/vsx/index.php?view=about.acknowledgments)
  says this text "would be appreciated":

  This research has made use of the International Variable Star Index (VSX) database, operated at AAVSO, Cambridge,
  Massachusetts, USA.

- Gaia DR3 eclipsing binaries: under Gaia above.

## Novelty catalogs and community records

Each citation is the one the record's Zenodo or Dataverse page gives. Every Zenodo record listed is CC BY 4.0.

- ExoMiner++: Martinho, M., & Valizadegan, H. (2025). ExoMiner++: Enhanced Transit Classification and a New Vetting
  Catalog for 2-Minute TESS Data [Dataset]. In Astronomical Journal (Version 1.0.0, Vol. 170, Issue 5, p. 287).
  Zenodo. https://doi.org/10.5281/zenodo.15466293
- ExoMiner++ 2.0: Martinho, M., & Valizadegan, H. (2025). ExoMiner++ 2.0: Vetting TESS Full-Frame Image Transit
  Signals (arXiv preprint) (Version 2.0.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.17707413
- RAVEN: Lafarga, M., Armstrong, D., Cui, K., Hadjigeorghiou, A., Kunovac, V., Doyle, L., Bryant, E., Díaz, R.,
  Nieto, L. A., & Osborn, A. (2026). Online material for article Automatic search for transiting planets in TESS-SPOC
  FFIs with RAVEN: over 100 newly validated planets and over 2000 vetted candidates [Dataset]. In Monthly Notices of
  the Royal Astronomical Society. Zenodo. https://doi.org/10.1093/mnras/stag512. That DOI is the article's; the data
  deposit the snapshot reads is Zenodo record 19661443 (https://zenodo.org/records/19661443).
- T16 (CC0 1.0): Roth, Joshua; Hartman, Joel; Bakos, Gaspar, 2026, "T16 Transit Search Cycle 1 Candidates Vetting
  Plots", https://doi.org/10.7910/DVN/CWEUGW, Harvard Dataverse, V3, UNF:6:jPC6JLw9EXUTM9mp7MgVnw== [fileUNF]
- Cao: Cao, E. (2026). Data deposit: 1,467 new transiting planet candidates from TESS [Dataset]. Zenodo.
  https://doi.org/10.5281/zenodo.23193828
- eumemic/exoplanets (https://github.com/eumemic/exoplanets): candidates and re-measured TCEs, read at a commit the
  snapshot's manifest records. Its README licenses the code under MIT and the results, tables and figures under
  CC BY 4.0, and asks for no citation.
- Single-object records:
  - Rabtsevich, P. (2026). A Pre-registered TESS Sector 110 Test of Two Transit-like Signals in TIC 4206066 (Version
    1.1). Zenodo. https://doi.org/10.5281/zenodo.23175179
  - Thawani, A. (2026). Preregistered transit predictions: TESS planet-candidate signal "Avijit" on TYC 717-2552-1
    (TIC 156733696) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.23271302
  - Thawani, A. (2026). Preregistered transit predictions: TESS planet-candidate signal "Niyati" on HD 354088
    (TIC 345494583) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.23271252
  - Barve, R. (2026). TIC 458191673.01: a 2.2 R⊕ planet candidate on a 2.57-day orbit around a nearby K dwarf, found
    in TESS full-frame images. Zenodo. https://doi.org/10.5281/zenodo.23293798
  - Ozturk, B. T. (2026). A faint dip in 2025, found again in 2018: an unconfirmed 2.5 Earth-radius planet candidate
    around the active K dwarf TIC 257484419 (Version 1.0). Zenodo. https://doi.org/10.5281/zenodo.23118499
  - Ozturk, B. T. (2026). A Planet Candidate on a 4.35-day Orbit around the Active K Dwarf TIC 257484419 (Version
    2.0). Zenodo. https://doi.org/10.5281/zenodo.23289148
  - Chopra, P. (2026). Predicted transit times for two TESS planet candidates: TIC 370612437 and HIP 114417
    [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.23257784
  - Th0rgal/open-exoplanet-hunt (https://github.com/Th0rgal/open-exoplanet-hunt), MIT: its candidate certificates,
    read at a commit the snapshot's manifest records. Its README asks for no citation.

## Literature search

Triage searches Zenodo, arXiv and OpenAlex by TIC for shortlisted signals. M3's vetting searches them again by every
name SIMBAD gives a vetted star, and searches NASA ADS by its object search.

- arXiv's API page (https://info.arxiv.org/help/api/index.html) asks all API users: "Acknowledge arXiv data usage with
  this statement on your product":

  Thank you to arXiv for use of its open access interoperability.

- OpenAlex's "Citing OpenAlex" page (https://help.openalex.org/how-to/citing-openalex/) asks for: Priem, J.,
  Piwowar, H., & Orr, R. (2022). OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and
  concepts. ArXiv. https://arxiv.org/abs/2205.01833
- NASA ADS's terms page (https://adsabs.github.io/help/terms/, read 2026-10-22) asks those who acknowledge its
  services to "use a phrase such as the following":

  This research has made use of the Astrophysics Data System, funded by NASA under Cooperative Agreement
  80NSSC25M7105.

## Software

lightkurve (Lightkurve Collaboration 2018), astropy (Astropy Collaboration 2013, 2018, 2022), astroquery
(Ginsburg et al. 2019), numpy, scipy, pandas, wotan (Hippke et al. 2019), transitleastsquares (Hippke & Heller
2019), batman (Kreidberg 2015), emcee (Foreman-Mackey et al. 2013), TRICERATOPS (Giacalone et al. 2021),
LEO-Vetter (Kunimoto et al. 2025), transit-diffImage, tess-point (Burke et al. 2020), SpiceyPy (Annex et al. 2020)
and the SPICE toolkit (Acton 1996; Acton et al. 2017).

- TRICERATOPS 1.1.0 (MIT), which the vetting stage runs for the false-positive probabilities. Its README
  (https://github.com/stevengiacalone/triceratops, as shipped with 1.1.0) asks users to "cite both the paper and the
  code":
  - Giacalone, S., Dressing, C. D., Jensen, E. L. N., et al. 2021, Vetting of 384 TESS Objects of Interest with
    TRICERATOPS and Statistical Validation of 12 Planet Candidates, AJ 161, 24 (doi:10.3847/1538-3881/abc6af)
  - Giacalone, S., & Dressing, C. D. 2020, triceratops: Candidate exoplanet rating tool, Astrophysics Source Code
    Library, ascl:2002.004
- LEO-Vetter (GPL-3.0). Its README (https://github.com/mkunimoto/LEO-Vetter) asks users to cite its paper:
  Kunimoto, M., Bryson, S., Jaffee, D., et al. (2025) The Astronomical Journal, 170, 280
- transit-diffImage (https://github.com/stevepur/transit-diffImage, by Steve Bryson, GPL-3.0), pinned at commit
  2b13199. Its README and setup.py at that commit ask for no citation (checked 2026-10-15); cite it by URL and commit.
- tess-point. Its README (https://github.com/christopherburke/tess-point) gives this citation: Burke, C. J., Levine,
  A., Fausnaugh, M., Vanderspek, R., Barclay, T., Libby-Roberts, J. E., Morris, B., Sipocz, B., Owens, M., Feinstein,
  A. D., Camacho, J., 2020, 0.4.1, Astrophysics Source Code Library, record ascl:2003:001
- TESScut (https://mast.stsci.edu/tesscut/), which runs Astrocut on MAST's servers. Its page asks: "If you use TESSCut
  for your work, please cite Brasseur et al. 2019". Its ASCL entry (https://ascl.net/1905.007): Brasseur, C. E.;
  Phillip, Carlita; Fleming, Scott W.; Mullally, S. E.; White, Richard L., Astrocut: Tools for creating cutouts of
  TESS images, ascl:1905.007 (2019ascl.soft05007B). Astrocut is BSD-3.
- SpiceyPy, which transit-diffImage uses for its barycentric correction. Its README
  (https://github.com/AndrewAnnex/SpiceyPy) says: "If you are publishing work that uses SpiceyPy, please cite
  SpiceyPy and the SPICE toolkit." Its citation: Annex et al., (2020). SpiceyPy: a Pythonic Wrapper for the SPICE
  Toolkit. Journal of Open Source Software, 5(46), 2050, https://doi.org/10.21105/joss.02050
- The SPICE toolkit, from NASA's Navigation and Ancillary Information Facility (NAIF). Its credit page
  (https://naif.jpl.nasa.gov/naif/credit.html) lists these references for NAIF:
  - Acton, C.H.; "Ancillary Data Services of NASA's Navigation and Ancillary Information Facility;" Planetary and
    Space Science, Vol. 44, No. 1, pp. 65-70, 1996. DOI 10.1016/0032-0633(95)00107-7
  - Charles Acton, Nathaniel Bachman, Boris Semenov, Edward Wright; A look toward the future in the handling of space
    science mission geometry; Planetary and Space Science (2017); DOI 10.1016/j.pss.2017.02.013
