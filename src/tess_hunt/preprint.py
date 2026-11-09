"""The preprint and dataset for a passed signal (decision 0043; M5 design, section 4.4). `tess-hunt preprint run`
renders a short paper from the signal's latest published record, whose call must be a pass that stands on it, and
lays beside it the dataset its numbers come from: each published record of the signal up to that one, the light curve
the passing vet read, and the density-prior posterior the run reproduces from it. The template is filled with
`substitute`, each value read by its key from the record, its runs' provenance and the published runs they name, so a
value they lack raises instead of rendering (docs/design.md, section 5.5). The PDF needs the optional `preprint`
dependency group."""

import datetime as dt
import json
import math
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from html import escape, unescape
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd

from tess_hunt import calls, prereg, vet, vetting
from tess_hunt.checks.families import good_timestamps, split
from tess_hunt.checks.physical import R_EARTH_PER_R_SUN
from tess_hunt.claims import CLAIMS, load_claims
from tess_hunt.config import runs_dir
from tess_hunt.ddt import _criteria, _from_triceratops, _number, _ppm
from tess_hunt.detrend import detrend
from tess_hunt.dossier import (
    SENTENCES,
    _f,
    _paper_id,
    _scrub,
    _table,
    _words,
)
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.fit import NAMES
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import publish_run, repo_root, sha256_file, start_run
from tess_hunt.transit import a_rs_from_density, light_curve
from tess_hunt.tricera import TWO_MINUTES_S

TEMPLATE = "results/preprints/preprint.template.md"
# Its text changes only with the maintainer's approval (decision 0043).
AUTHOR = "results/preprints/author.toml"
AUTHOR_KEYS = ("given_names", "family_names", "affiliation", "repository")
AUTHOR_OPTIONAL = ("orcid", "email")
DOIS = "results/predictions/dois.toml"
SECTORS = "benchmarks/tess_sectors.csv"
# The injection-recovery run's recovered fraction by expected SNR, which the paper points to.
COMPLETENESS = "completeness_snr.csv"
EXOFOP_STAR = "https://exofop.ipac.caltech.edu/tess/target.php?id={}"
# The record's plots the paper shows. Its centroid plots draw Gaia DR3 stars, so they stay in the dataset under Gaia's
# terms and the paper is CC BY 4.0 whole.
FIGURES = ("transits.png", "folds.png", "odd_even.png", "phase.png")
# The paper's own captions for them, as plots.py draws them: the dossier's assume a reader inside the project. Each
# opens with a phrase and no article (AAS).
CAPTIONS = {
    "transits.png": "Each predicted transit in the light curve, one panel per transit, as relative flux against time "
    "from the predicted mid-transit time. Panel titles give the epoch (counted from <i>T</i><sub>0</sub>) and the "
    "sector. "
    "Grey points are individual cadences, and blue points are medians in bins one-eighth of the search's box duration "
    "(Section 4) wide. The shaded band spans the box duration. Panels with few points lie at the edge of a data gap",
    "folds.png": "Light curve folded on the ephemeris, one panel per season and light-curve family. Panel titles give "
    "the family (`pdcsap` for PDCSAP flux from SPOC or TESS-SPOC, `qlp` for QLP flux), the season (counted from 0) and "
    "its sectors. Points and band are as in Figure 1",
    "odd_even.png": "Odd-numbered (left) and even-numbered (right) transits, folded separately. Points and band are "
    "as in Figure 1. The red line marks the median flux in the transit core (the central half of the search's box "
    "duration, Section 4), taken separately for the odd and the even transits",
    "phase.png": "Relative flux vs. orbital phase over the whole orbit, with the transit at phase 0 and phases from "
    "−0.25 to 0.75, so a phase above 0.75 is drawn one orbit earlier. Grey points are individual cadences, and blue "
    "points are medians in bins half the search's box duration (Section 4) wide. The dashed line marks phase 0.5, "
    "where a secondary eclipse falls if the orbit is circular. The red line marks the most significant secondary event "
    "ModShift finds at any phase, labelled with its phase and significance",
}
PACKAGE = ["preprint.md", "preprint.pdf", "manifest.json", "provenance.json", *FIGURES]
# The density-prior posterior the run reproduces, in the dataset: Table 1's depth, duration and radius come from its
# samples.
POSTERIOR = "posterior-prior.npz"
CC_BY = "CC BY 4.0"
GAIA = "CC BY-NC 3.0 IGO"
# A record's files that hold Gaia DR3 data, as results/README.md lists them, by their path in the record.
GAIA_FILES = {
    "checks.json",
    "checks-with-suspect.json",
    "neighbours.csv",
    "triceratops.json",
    "plots/centroids.png",
    "pixels.png",
    "review.json",
    "review-scripts.tar.gz",
    "dossier.md",
}
# A record's files that hold ExoFOP's rows, which stay under ExoFOP's terms whatever the file's licence.
EXOFOP_FILES = {"literature.json", "claims.json", "dossier.md"}
EXOFOP = "ExoFOP's rows stay under ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php)"
SPECIMEN = "SPECIMEN: not a candidate"
# What each check asks, for a reader outside the project; a check missing here raises, so a new one is named first.
CHECKS = {
    "novelty": "Known objects at the period",
    "odd_even": "Odd against even transit depths",
    "secondary": "A dip at phase 0.5",
    "sector_depth": "Depth from sector to sector",
    "holdout": "Held-out seasons",
    "signal_present": "The dip's significance",
    "shape": "Transit shape",
    "density": "Transit stellar density against the TIC's",
    "radius": "The transiting body's radius",
    "neighbours": "Gaia DR3 neighbours that could make the dip",
    "pixels": "Difference-image centroid offset",
    "triceratops": "TRICERATOPS's false-positive probabilities",
    "literature": "Papers and ExoFOP listings",
}
# The question each of the review's lenses concerns: the dossier's short labels read as verdicts beside a finding.
QUESTIONS = {
    "on_star": "whether the signal is on the star",
    "planet": "whether the signal is a planet",
    "real_new": "whether the signal is real and new",
}
IS = {"pass": "passes", "fail": "fails", "inconclusive": "is inconclusive"}
WAS = {"pass": "passed", "fail": "failed", "inconclusive": "was inconclusive"}
# Counts from one to nine are spelled out in the paper's prose; measured values stay numerals.
SPELLED = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MINUS = "−"
ORDINALS = {
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
}
# How a listing's period relates to the signal's, by the novelty harmonic k it matched at (the signal's period is the
# listing's times k).
HARMONICS = {
    1.0: "this period",
    0.5: "twice this period",
    2.0: "half this period",
    1 / 3: "three times this period",
    3.0: "a third of this period",
}
# Why the held-out check could not test a season whose record gives a status and no reason.
UNTESTED = {
    "underpowered": "the depth expected there is too small against its error",
    "no_predicted_transit_in_data": "too few cadences fall in the predicted cores",
}
# The Abstract's word on a preregistered result, after the sentence on the deposit, and the Conclusions'.
SUMMARY_RESULT = {
    "replicated": " The transits appeared at the predicted times.",
    "missed": " The transits were absent at the predicted times.",
    "pending": " The preregistered test of that prediction is not yet judged.",
    "untested": " The new data could not test that prediction.",
}
CONCLUSION_RESULT = {
    "replicated": " The transits recurred at the times we preregistered.",
    "missed": " The transits were absent at the times we preregistered.",
    "pending": " The preregistered test of the transits in later sectors is not yet judged.",
    "untested": " The later sectors could not test our preregistered prediction.",
}
# The products' names in prose, where they differ from prereg.PRODUCTS.
PRODUCT_NAMES = {"SPOC 2-min": "SPOC 2-minute"}
PDCSAP = ("SPOC 2-min", "TESS-SPOC")
# Every work the paper cites, by key: the citation it takes in the text and its entry in AAS form, each checked in NASA
# ADS (the MAST and ExoFOP data DOIs, which ADS does not index, in DataCite) on 2026-11-05. The references list holds
# the ones a record's paper cites, sorted as AAS sorts them.
REFERENCES = {
    "acton1996": (
        "Acton 1996",
        "Acton, C. H. 1996, P&SS, 44, 65, doi: 10.1016/0032-0633(95)00107-7",
    ),
    "acton2018": (
        "Acton et al. 2018",
        "Acton, C., Bachman, N., Semenov, B., & Wright, E. 2018, P&SS, 150, 9, doi: 10.1016/j.pss.2017.02.013",
    ),
    "annex2020": (
        "Annex et al. 2020",
        "Annex, A., Pearson, B., Seignovert, B., et al. 2020, JOSS, 5, 2050, doi: 10.21105/joss.02050",
    ),
    "astropy2013": (
        "Astropy Collaboration et al. 2013",
        "Astropy Collaboration, Robitaille, T. P., Tollerud, E. J., et al. 2013, A&A, 558, A33, doi: "
        "10.1051/0004-6361/201322068",
    ),
    "astropy2018": (
        "Astropy Collaboration et al. 2018",
        "Astropy Collaboration, Price-Whelan, A. M., Sipőcz, B. M., et al. 2018, AJ, 156, 123, doi: "
        "10.3847/1538-3881/aabc4f",
    ),
    "astropy2022": (
        "Astropy Collaboration et al. 2022",
        "Astropy Collaboration, Price-Whelan, A. M., Lim, P. L., et al. 2022, ApJ, 935, 167, doi: "
        "10.3847/1538-4357/ac7c74",
    ),
    "boch2012": ("Boch et al. 2012", "Boch, T., Pineau, F., & Derriere, S. 2012, ASPC, 461, 291"),
    "brasseur2019": (
        "Brasseur et al. 2019",
        "Brasseur, C. E., Phillip, C., Fleming, S. W., Mullally, S. E., & White, R. L. 2019, Astrocut: Tools for "
        "creating cutouts of TESS images, Astrophysics Source Code Library, record ascl:1905.007",
    ),
    "bryson2013": (
        "Bryson et al. 2013",
        "Bryson, S. T., Jenkins, J. M., Gilliland, R. L., et al. 2013, PASP, 125, 889, doi: 10.1086/671767",
    ),
    "burke2020": (
        "Burke et al. 2020",
        "Burke, C. J., Levine, A., Fausnaugh, M., et al. 2020, TESS-Point: High precision TESS pointing tool, "
        "Astrophysics Source Code Library, record ascl:2003.001",
    ),
    "caldwell2020a": (
        "Caldwell et al. 2020a",
        "Caldwell, D. A., Tenenbaum, P., Twicken, J. D., et al. 2020a, RNAAS, 4, 201, doi: 10.3847/2515-5172/abc9b3",
    ),
    "caldwell2020b": (
        "Caldwell et al. 2020b",
        'Caldwell, D. A., Jenkins, J. M., & Ting, E. B. 2020b, TESS Light Curves From Full Frame Images ("TESS-SPOC"), '
        "STScI/MAST, doi: 10.17909/t9-wpz1-8s54",
    ),
    "christiansen2025": (
        "Christiansen et al. 2025",
        "Christiansen, J. L., McElroy, D. L., Harbut, M., et al. 2025, PSJ, 6, 186, doi: 10.3847/PSJ/ade3c2",
    ),
    "coughlin2016": (
        "Coughlin et al. 2016",
        "Coughlin, J. L., Mullally, F., Thompson, S. E., et al. 2016, ApJS, 224, 12, doi: 10.3847/0067-0049/224/1/12",
    ),
    "creevey2023": (
        "Creevey et al. 2023",
        "Creevey, O. L., Sordo, R., Pailler, F., et al. 2023, A&A, 674, A26, doi: 10.1051/0004-6361/202243688",
    ),
    "foremanmackey2013": (
        "Foreman-Mackey et al. 2013",
        "Foreman-Mackey, D., Hogg, D. W., Lang, D., & Goodman, J. 2013, PASP, 125, 306, doi: 10.1086/670067",
    ),
    "gaia2016": (
        "Gaia Collaboration et al. 2016",
        "Gaia Collaboration, Prusti, T., de Bruijne, J. H. J., et al. 2016, A&A, 595, A1, doi: "
        "10.1051/0004-6361/201629272",
    ),
    "gaia2023": (
        "Gaia Collaboration et al. 2023",
        "Gaia Collaboration, Vallenari, A., Brown, A. G. A., et al. 2023, A&A, 674, A1, doi: "
        "10.1051/0004-6361/202243940",
    ),
    "giacalone2020": (
        "Giacalone & Dressing 2020",
        "Giacalone, S., & Dressing, C. D. 2020, triceratops: Candidate exoplanet rating tool, Astrophysics Source Code "
        "Library, record ascl:2002.004",
    ),
    "giacalone2021": (
        "Giacalone et al. 2021",
        "Giacalone, S., Dressing, C. D., Jensen, E. L. N., et al. 2021, AJ, 161, 24, doi: 10.3847/1538-3881/abc6af",
    ),
    "ginsburg2019": (
        "Ginsburg et al. 2019",
        "Ginsburg, A., Sipőcz, B. M., Brasseur, C. E., et al. 2019, AJ, 157, 98, doi: 10.3847/1538-3881/aafc33",
    ),
    "guerrero2021": (
        "Guerrero et al. 2021",
        "Guerrero, N. M., Seager, S., Huang, C. X., et al. 2021, ApJS, 254, 39, doi: 10.3847/1538-4365/abefe1",
    ),
    "hippke2019a": (
        "Hippke & Heller 2019",
        "Hippke, M., & Heller, R. 2019, A&A, 623, A39, doi: 10.1051/0004-6361/201834672",
    ),
    "hippke2019b": (
        "Hippke et al. 2019",
        "Hippke, M., David, T. J., Mulders, G. D., & Heller, R. 2019, AJ, 158, 143, doi: 10.3847/1538-3881/ab3984",
    ),
    "huang2020": (
        "Huang 2020",
        'Huang, C. X. 2020, TESS Lightcurves From The MIT Quick-Look Pipeline ("QLP"), STScI/MAST, doi: '
        "10.17909/t9-r086-e880",
    ),
    "huang2020a": (
        "Huang et al. 2020a",
        "Huang, C. X., Vanderburg, A., Pál, A., et al. 2020a, RNAAS, 4, 204, doi: 10.3847/2515-5172/abca2e",
    ),
    "huang2020b": (
        "Huang et al. 2020b",
        "Huang, C. X., Vanderburg, A., Pál, A., et al. 2020b, RNAAS, 4, 206, doi: 10.3847/2515-5172/abca2d",
    ),
    "hunter2007": ("Hunter 2007", "Hunter, J. D. 2007, CSE, 9, 90, doi: 10.1109/MCSE.2007.55"),
    "jenkins2016": (
        "Jenkins et al. 2016",
        "Jenkins, J. M., Twicken, J. D., McCauliff, S., et al. 2016, Proc. SPIE, 9913, 99133E, doi: 10.1117/12.2233418",
    ),
    "justesen2021": (
        "Justesen & Albrecht 2021",
        "Justesen, A. B., & Albrecht, S. 2021, ApJ, 912, 123, doi: 10.3847/1538-4357/abefcd",
    ),
    "kipping2013": (
        "Kipping 2013",
        "Kipping, D. M. 2013, MNRAS, 435, 2152, doi: 10.1093/mnras/stt1435",
    ),
    "kostov2025": (
        "Kostov et al. 2025",
        "Kostov, V. B., Powell, B. P., Fornear, A. U., et al. 2025, ApJS, 279, 50, doi: 10.3847/1538-4365/ade2d8",
    ),
    "kovacs2002": (
        "Kovács et al. 2002",
        "Kovács, G., Zucker, S., & Mazeh, T. 2002, A&A, 391, 369, doi: 10.1051/0004-6361:20020802",
    ),
    "kreidberg2015": ("Kreidberg 2015", "Kreidberg, L. 2015, PASP, 127, 1161, doi: 10.1086/683602"),
    "kunimoto2021": (
        "Kunimoto et al. 2021",
        "Kunimoto, M., Huang, C., Tey, E., et al. 2021, RNAAS, 5, 234, doi: 10.3847/2515-5172/ac2ef0",
    ),
    "kunimoto2022": (
        "Kunimoto et al. 2022",
        "Kunimoto, M., Tey, E., Fong, W., et al. 2022, RNAAS, 6, 236, doi: 10.3847/2515-5172/aca158",
    ),
    "kunimoto2025": (
        "Kunimoto et al. 2025",
        "Kunimoto, M., Bryson, S., Jaffee, D., et al. 2025, AJ, 170, 280, doi: 10.3847/1538-3881/ae070a",
    ),
    "lightkurve2018": (
        "Lightkurve Collaboration et al. 2018",
        "Lightkurve Collaboration, Cardoso, J. V. d. M., Hedges, C., et al. 2018, Lightkurve: Kepler and TESS time "
        "series analysis in Python, Astrophysics Source Code Library, record ascl:1812.013",
    ),
    "lindegren2021": (
        "Lindegren et al. 2021",
        "Lindegren, L., Klioner, S. A., Hernández, J., et al. 2021, A&A, 649, A2, doi: 10.1051/0004-6361/202039709",
    ),
    "martinho2025a": (
        "Martinho & Valizadegan 2025a",
        "Martinho, M., & Valizadegan, H. 2025a, ExoMiner++: Enhanced Transit Classification and a New Vetting Catalog "
        "for 2-Minute TESS Data, Zenodo, doi: 10.5281/zenodo.15466293",
    ),
    "martinho2025b": (
        "Martinho & Valizadegan 2025b",
        "Martinho, M., & Valizadegan, H. 2025b, ExoMiner++ 2.0: Vetting TESS Full-Frame Image Transit Signals, Zenodo, "
        "doi: 10.5281/zenodo.17707413",
    ),
    "mowlavi2023": (
        "Mowlavi et al. 2023",
        "Mowlavi, N., Holl, B., Lecoeur-Taïbi, I., et al. 2023, A&A, 674, A16, doi: 10.1051/0004-6361/202245330",
    ),
    "nexsci2022": (
        "NExScI 2022",
        "NExScI 2022, Exoplanet Follow-up Observing Program Web Service, IPAC, doi: 10.26134/ExoFOP5",
    ),
    "ochsenbein2000": (
        "Ochsenbein et al. 2000",
        "Ochsenbein, F., Bauer, P., & Marcout, J. 2000, A&AS, 143, 23, doi: 10.1051/aas:2000169",
    ),
    "paegert2021": (
        "Paegert et al. 2021",
        "Paegert, M., Stassun, K. G., Collins, K. A., et al. 2021, arXiv e-prints, arXiv:2108.04778, doi: "
        "10.48550/arXiv.2108.04778",
    ),
    "parviainen2015": (
        "Parviainen 2015",
        "Parviainen, H. 2015, MNRAS, 450, 3233, doi: 10.1093/mnras/stv894",
    ),
    "pineau2020": (
        "Pineau et al. 2020",
        "Pineau, F.-X., Boch, T., Derrière, S., & Schaaff, A. 2020, ASPC, 522, 125",
    ),
    "pont2006": (
        "Pont et al. 2006",
        "Pont, F., Zucker, S., & Queloz, D. 2006, MNRAS, 373, 231, doi: 10.1111/j.1365-2966.2006.11012.x",
    ),
    "priem2022": (
        "Priem et al. 2022",
        "Priem, J., Piwowar, H., & Orr, R. 2022, arXiv e-prints, arXiv:2205.01833, doi: 10.48550/arXiv.2205.01833",
    ),
    "prsa2022a": (
        "Prša et al. 2022a",
        "Prša, A., Kochoska, A., Conroy, K. E., et al. 2022a, ApJS, 258, 16, doi: 10.3847/1538-4365/ac324a",
    ),
    "prsa2022b": (
        "Prša et al. 2022b",
        'Prša, A., Kochoska, A., Conroy, K., et al. 2022b, TESS Eclipsing Binaries ("TESS-EBs"), STScI/MAST, doi: '
        "10.17909/t9-9gm4-fx30",
    ),
    "ricker2015": (
        "Ricker et al. 2015",
        "Ricker, G. R., Winn, J. N., Vanderspek, R., et al. 2015, JATIS, 1, 014003, doi: 10.1117/1.JATIS.1.1.014003",
    ),
    "riello2021": (
        "Riello et al. 2021",
        "Riello, M., De Angeli, F., Evans, D. W., et al. 2021, A&A, 649, A3, doi: 10.1051/0004-6361/202039587",
    ),
    "rowe2015": (
        "Rowe et al. 2015",
        "Rowe, J. F., Coughlin, J. L., Antoci, V., et al. 2015, ApJS, 217, 16, doi: 10.1088/0067-0049/217/1/16",
    ),
    "smith2012": (
        "Smith et al. 2012",
        "Smith, J. C., Stumpe, M. C., Van Cleve, J. E., et al. 2012, PASP, 124, 1000, doi: 10.1086/667697",
    ),
    "stassun2019": (
        "Stassun et al. 2019",
        "Stassun, K. G., Oelkers, R. J., Paegert, M., et al. 2019, AJ, 158, 138, doi: 10.3847/1538-3881/ab3467",
    ),
    "stumpe2012": (
        "Stumpe et al. 2012",
        "Stumpe, M. C., Smith, J. C., Van Cleve, J. E., et al. 2012, PASP, 124, 985, doi: 10.1086/667698",
    ),
    "stumpe2014": (
        "Stumpe et al. 2014",
        "Stumpe, M. C., Smith, J. C., Catanzarite, J. H., et al. 2014, PASP, 126, 100, doi: 10.1086/674989",
    ),
    "tessteam2018": (
        "TESS Team 2018",
        "TESS Team 2018, TESS Input Catalog and Candidate Target List, STScI/MAST, doi: 10.17909/fwdt-2x66",
    ),
    "tessteam2021": (
        "TESS Team 2021",
        "TESS Team 2021, TESS Light Curves - All Sectors, STScI/MAST, doi: 10.17909/t9-nmc8-f686",
    ),
    "tessteam2022": (
        "TESS Team 2022",
        "TESS Team 2022, TESS Calibrated Full Frame Images: All Sectors, STScI/MAST, doi: 10.17909/0cp4-2j79",
    ),
    "watson2006": (
        "Watson et al. 2006",
        "Watson, C. L., Henden, A. A., & Price, A. 2006, SASS, 25, 47",
    ),
    "wenger2000": (
        "Wenger et al. 2000",
        "Wenger, M., Ochsenbein, F., Egret, D., et al. 2000, A&AS, 143, 9, doi: 10.1051/aas:2000332",
    ),
}
# The works every paper cites in its fixed text and its Software line.
CITED = (
    "acton1996",
    "acton2018",
    "annex2020",
    "astropy2013",
    "astropy2018",
    "astropy2022",
    "boch2012",
    "brasseur2019",
    "bryson2013",
    "burke2020",
    "christiansen2025",
    "coughlin2016",
    "creevey2023",
    "foremanmackey2013",
    "gaia2016",
    "gaia2023",
    "giacalone2020",
    "giacalone2021",
    "ginsburg2019",
    "guerrero2021",
    "hippke2019a",
    "hippke2019b",
    "huang2020a",
    "hunter2007",
    "jenkins2016",
    "justesen2021",
    "kipping2013",
    "kostov2025",
    "kovacs2002",
    "kreidberg2015",
    "kunimoto2025",
    "lightkurve2018",
    "lindegren2021",
    "martinho2025a",
    "martinho2025b",
    "mowlavi2023",
    "nexsci2022",
    "ochsenbein2000",
    "paegert2021",
    "parviainen2015",
    "pineau2020",
    "pont2006",
    "priem2022",
    "prsa2022a",
    "prsa2022b",
    "ricker2015",
    "riello2021",
    "rowe2015",
    "stassun2019",
    "tessteam2018",
    "tessteam2022",
    "watson2006",
    "wenger2000",
)
# Each light-curve product's papers and data DOI entry, cited where the paper names the product; PDCSAP's papers
# with the products whose flux is PDCSAP.
PRODUCT_REFERENCES = {
    "SPOC 2-min": ("jenkins2016", "tessteam2021"),
    "TESS-SPOC": ("caldwell2020a", "caldwell2020b"),
    "QLP": ("huang2020a", "huang2020b", "kunimoto2021", "kunimoto2022", "huang2020"),
}
PDCSAP_REFERENCES = ("smith2012", "stumpe2012", "stumpe2014")
SOFTWARE = (
    "Astrocut (Brasseur et al. 2019), astropy (Astropy Collaboration et al. 2013, 2018, 2022), astroquery (Ginsburg "
    "et al. 2019), batman (Kreidberg 2015), emcee (Foreman-Mackey et al. 2013), LEO-Vetter (Kunimoto et al. 2025), "
    "lightkurve (Lightkurve Collaboration et al. 2018), matplotlib (Hunter 2007), PyTransit (Parviainen 2015), SPICE "
    "(Acton 1996; Acton et al. 2018), SpiceyPy (Annex et al. 2020), tess-point (Burke et al. 2020), "
    "transit-diffImage, transitleastsquares (Hippke & Heller 2019), TRICERATOPS (Giacalone & "
    "Dressing 2020; Giacalone et al. 2021) and wotan (Hippke et al. 2019)"
)
# transit-diffImage asks for no citation, so the paper gives its author, URL and the commit tess-hunt pins.
DIFFIMAGE = "https://github.com/stevepur/transit-diffImage"
# What each of a record's files holds, for the dataset's guide, in the order the paper lists them. A pattern ending in
# "/" is a directory; one with "*" matches file names.
GUIDE = (
    (
        "checks.json",
        "each vetting check's outcome, reason and evidence, both fits, the red-noise factors and the neighbour check "
        "with its table",
    ),
    (
        "neighbours.csv",
        "the Gaia DR3 stars near the target, with the eclipse depth each would need to produce the transit",
    ),
    (
        "checks-with-suspect.json",
        "the same checks with the timing-suspect sectors kept in, for comparison only",
    ),
    (
        "triceratops.json",
        "TRICERATOPS's runs: its probabilities, the stars it modelled and the transit depth it assigned each",
    ),
    ("probs.csv", "TRICERATOPS's probability for each scenario"),
    ("pixels.json", "the second list's pixel check"),
    (
        "literature.json",
        "the literature search: the names searched, the papers found and ExoFOP's rows for the star",
    ),
    (
        "claims.json",
        "the claim, the listings sorted under DR 0042, and the rerun novelty check",
    ),
    ("prereg.json", "the preregistered test's result"),
    ("merge.json", "what a new vetting's light curve changed"),
    ("review.json", "the review: each finding with its rating and its refuters' verdicts"),
    ("review-notes.toml", "the dated notes on the review's quoted text"),
    ("review-scripts.tar.gz", "the scripts the review ran"),
    ("call.toml", "the call"),
    (
        "provenance-*.json",
        "one run's commit, criteria and command, for the files that run wrote",
    ),
    ("plots/", "the record's figures, including the centroid plot"),
    ("pixels.png", "the second list's centroid plot"),
    ("dossier.md", "tess-hunt's account of the record, in prose"),
)
# ACKNOWLEDGEMENTS.md's Gaia acknowledgement. The Gaia DR3 papers it asks for are in REFERENCES.
GAIA_CREDIT = (
    " This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), "
    "processed by the Gaia Data Processing and Analysis Consortium (DPAC, "
    "https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national "
    "institutions, in particular the institutions participating in the Gaia Multilateral Agreement."
)
# AASTeX's look: a Times-like face (STIX Two Math only for ⊕, ⊙ and ⋆, which the text face lacks), justified and
# hyphenated text, a centred title block, numbered capitalised section heads (the toc extension's ids pick out the
# unnumbered back matter), errors stacked, tables at the text width with horizontal rules only and rows kept whole,
# and figures at the text width with a bold label. No footnotes: WeasyPrint 70 sets them a page or more after their
# call, with footnote-policy: line too, so URLs go in Data Availability.
UNNUMBERED = "h2#abstract, h2#acknowledgements, h2#use-of-llms, h2#data-availability, h2#references, h2[id^='appendix']"
STYLE = f"""
@page {{ size: A4; margin: 2cm; @bottom-right {{ content: counter(page); font-size: 9pt; }} }}
html {{ font-family: "STIX Two Text", "STIX Two Math", "TeX Gyre Termes", serif; font-size: 10.5pt; line-height: 1.3; }}
body {{ text-align: justify; hyphens: auto; counter-reset: section; }}
h1 {{ font-size: 15pt; text-align: center; hyphens: none; margin: 0.4em 0; }}
.front {{ text-align: center; margin-bottom: 1.2em; }}
.front p {{ margin: 0.15em 0; }}
h2, h3 {{ text-align: left; hyphens: none; break-after: avoid; }}
h2 {{ font-size: 10.5pt; text-transform: uppercase; letter-spacing: 0.04em; margin: 1.4em 0 0.5em;
  counter-increment: section; counter-reset: subsection; }}
h2::before {{ content: counter(section) ". "; }}
{UNNUMBERED} {{ counter-increment: none; }}
{", ".join(f"{h}::before" for h in UNNUMBERED.split(", "))} {{ content: none; }}
h2#abstract {{ text-align: center; }}
h3 {{ font-size: 10.5pt; font-style: italic; font-weight: normal; margin: 1em 0 0.4em; counter-increment: subsection; }}
h3::before {{ content: counter(section) "." counter(subsection) ". "; }}
sub, sup {{ font-size: 70%; line-height: 0; position: relative; vertical-align: baseline; }}
sup {{ top: -0.45em; }}
sub {{ top: 0.25em; }}
.pm {{ display: inline-block; vertical-align: -0.3em; line-height: 1; }}
.pm sup, .pm sub {{ display: block; position: static; line-height: 1.1; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; border-top: 1pt solid; border-bottom: 1pt solid;
  margin: 0.4em 0; break-before: avoid; }}
th {{ border-bottom: 0.5pt solid; }}
th, td {{ padding: 2pt 5pt; vertical-align: top; text-align: left; hyphens: none; }}
tr {{ break-inside: avoid; }}
table + p {{ font-size: 9pt; }}
figure {{ break-inside: avoid; margin: 1em 0; }}
figure img {{ width: 100%; }}
figcaption {{ font-size: 9pt; }}
code {{ font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; hyphens: none; overflow-wrap: anywhere; }}
.id {{ hyphens: none; white-space: nowrap; }}
.names {{ hyphens: manual; text-align: left; }}
.references p {{ padding-left: 1.5em; text-indent: -1.5em; margin: 0 0 1pt; font-size: 9pt; text-align: left;
  hyphens: none; }}
"""
SPECIMEN_STYLE = f"""
@page {{ @top-center {{ content: "{SPECIMEN}"; }} @bottom-center {{ content: "{SPECIMEN}"; }} }}
"""
ZENODO = Template("""\
# Zenodo deposit form for $run_id

## Resource type

Publication / Preprint

## Title

$title

## Creators

$creators

## Description

$description

## Licence

- Creative Commons Attribution 4.0 International (CC BY 4.0): the paper, its figures and the dataset's other files
- Creative Commons Attribution-NonCommercial 3.0 IGO (CC BY-NC 3.0 IGO), ESA's terms for Gaia data
  (https://www.cosmos.esa.int/web/gaia-users/license): the dataset's files that hold Gaia DR3 data, which the
  description lists
- ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php): ExoFOP's rows in the dataset's `literature.json`,
  `claims.json` and `dossier.md`, and the ExoFOP listings the paper names

## Related identifiers

$related

## Keywords

- TESS
- transiting exoplanets
- planet candidates

## Files

Upload `preprint.pdf`, `preprint.md`, the figures (`$figures`), `manifest.json` and `provenance.json` from the run
directory. Upload its `dataset/` directory as one zip archive, so its folders are kept. `manifest.json` lists every
file in `dataset/` with its sha256.
""")


def passed_record(signal: Path) -> Path:
    """The signal's latest published record, when its call is a pass that stands on it and git shows no change under
    the signal's directory. Raises SystemExit otherwise, before anything is made."""
    where = f"results/vetting/{signal.name}"
    # The paper reads the record as it was published and committed; checked first, so the reasons below are the
    # committed record's.
    if prereg._uncommitted(signal):
        raise SystemExit(
            f"{where} has changes that are not committed; the paper reads the record as published"
        )
    records = vetting._records(signal)
    if not records:
        raise SystemExit(f"no published record in {where}")
    record = records[-1]
    label = vetting._label(record)
    found = calls.problems(record)
    if found:
        raise SystemExit(
            f"refused: the call in {signal.name}'s latest record, {label}, does not stand on it:\n"
            + "\n".join(f"- {p}" for p in found)
        )
    outcome = calls.load(record / "call.toml")["outcome"]
    if outcome != "passed":
        raise SystemExit(
            f"{signal.name}'s latest record, {label}, is {outcome}: only a pass that stands gets a preprint"
        )
    return record


def load_author(path: Path) -> dict:
    """The author line and the repository URL the paper gives, from `author.toml`."""
    if not path.is_file():
        raise SystemExit(
            f"no {AUTHOR}: the author line waits on the maintainer's approval (decision 0043)"
        )
    author = tomllib.loads(path.read_text())
    keys = set(author)
    if (
        not set(AUTHOR_KEYS) <= keys <= set(AUTHOR_KEYS + AUTHOR_OPTIONAL)
        or not all(isinstance(v, str) and v.strip() for v in author.values())
        or not author["repository"].startswith("https://")
    ):
        raise SystemExit(
            f"{path.name} needs {', '.join(AUTHOR_KEYS)} as text, repository an https URL, and may give "
            f"{' and '.join(AUTHOR_OPTIONAL)}"
        )
    return author


def _versions(record: Path) -> list[Path]:
    """The signal's published records before `record`, in order, then `record` itself."""
    number = calls.version(record) or 1
    earlier = [
        r for r in vetting._records(vetting._signal_dir(record)) if (calls.version(r) or 1) < number
    ]
    return [*earlier, record]


def _record_paths(record: Path) -> dict[str, Path]:
    """Each file in the directories of the signal's published records up to `record`, by its path under the
    dataset's `vetting/`, as results/vetting/ holds it."""
    signal = vetting._signal_dir(record)
    out = {}
    for r in _versions(record):
        for path in sorted(r.rglob("*")):
            # A version's directory sits inside the M3 record's and is a record of its own.
            if path.is_file() and calls.version(r / path.relative_to(r).parts[0]) is None:
                out[f"vetting/{signal.name}/{path.relative_to(signal)}"] = path
    return out


def record_files(record: Path) -> dict[str, Path]:
    """The records' files that git tracks: a file git ignores, such as macOS's .DS_Store, is no part of a record."""
    signal = vetting._signal_dir(record)
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=signal, capture_output=True, text=True, check=True
    ).stdout
    tracked = {signal / name for name in listed.split("\0") if name}
    return {name: path for name, path in _record_paths(record).items() if path in tracked}


def _light_curve(record: Path) -> tuple[str, Path]:
    """The light curve `record`'s vetting run read, by its path under the dataset, checked against the sha256 the run
    recorded."""
    made = json.loads((record / "provenance-checks.json").read_text())
    tic = int(json.loads((record / "checks.json").read_text())["tic"])
    path = vetting._light_curves(made) / f"{tic}.npz"
    if not path.is_file() or sha256_file(path) != made["inputs"].get(f"light_curve_{tic}", {}).get(
        "sha256"
    ):
        raise SystemExit(
            f"the light curve on disk for TIC {tic} is not the one {made['run_id']} read"
        )
    return f"lc/{tic}.npz", path


def dataset(record: Path) -> dict[str, Path]:
    """The dataset's files by their path under `dataset/`: the signal's published records up to `record` and the
    light curve its vetting run read."""
    name, path = _light_curve(record)
    return record_files(record) | {name: path}


def _in_record(path: str) -> str:
    """A dataset file's path within its record, from its path under `dataset/`: `vetting/NAME/r2/plots/x.png` is
    `plots/x.png`."""
    parts = Path(path).parts
    inside = parts[2:] if parts[0] == "vetting" else parts
    if inside and calls.version(Path(inside[0])):
        inside = inside[1:]
    return "/".join(inside)


def licence(path: str) -> dict[str, str]:
    """A dataset file's licence by its path under `dataset/` (results/README.md): a record's file holding Gaia DR3 data
    stays under ESA's terms, ExoFOP's rows stay under ExoFOP's, and the rest is CC BY 4.0."""
    name = _in_record(path)
    found = {"licence": GAIA if name in GAIA_FILES else CC_BY}
    if name in EXOFOP_FILES:
        found["exofop"] = EXOFOP
    return found


def _spell(n: int) -> str:
    """A count in words up to nine, and a numeral above, with a thousands separator from five digits (AAS)."""
    if 0 <= n < len(SPELLED):
        return SPELLED[n]
    return f"{n:,}" if n >= 10000 else str(n)


def _count(n: int, word: str) -> str:
    return f"{_spell(n)} {word}" + ("" if n == 1 else "s")


def _date(value) -> str:
    """A date in the paper's prose as AAS journals print it, 2027 January 20; run ids keep their own form."""
    day = dt.date.fromisoformat(str(value)[:10])
    return f"{day.year} {MONTHS[day.month - 1]} {day.day}"


def _signed(text: str) -> str:
    return text.replace("-", MINUS)


def _spread(value: dict, fmt: str) -> str:
    """A median with its distances to the 16th and 84th percentiles: one ± when they agree at the printed precision,
    otherwise a superscript and a subscript."""
    median = _signed(f"{value['median']:{fmt}}")
    plus, minus = f"{value['plus']:{fmt}}", f"{value['minus']:{fmt}}"
    if plus == minus:
        return f"{median} ± {plus}"
    # The span stacks the pair, one above the other, as AAS sets it.
    return f'{median}<span class="pm"><sup>+{plus}</sup><sub>{MINUS}{minus}</sub></span>'


def _mean_sd(mean: float, sd: float, runs: int) -> str:
    """A mean over TRICERATOPS's runs with their standard deviation, both to the deviation's first significant
    figure (its first two when that figure is 1). One run has no spread, so it gives the mean alone."""
    if runs < 2 or not sd > 0:
        return _number(mean, ".3g")
    scale = math.floor(math.log10(sd))
    if f"{sd:e}".startswith("1"):
        scale -= 1
    if scale >= -5:
        places = max(0, -scale)
        return f"{mean:.{places}f} ± {sd:.{places}f}"
    exponent = math.floor(math.log10(mean)) if mean > 0 else scale
    places = max(0, exponent - scale)
    unit = 10.0**exponent
    return f"({mean / unit:.{places}f} ± {sd / unit:.{places}f}) × 10<sup>{_signed(str(exponent))}</sup>"


def _id(text: str) -> str:
    """An identifier kept on one line: a break at one of its hyphens would read as a hyphenated word."""
    return f'<span class="id">{text}</span>'


def _doi(doi: str) -> str:
    """A DOI in running text, kept on one line and from hyphenation, which would break it with a hyphen it does not
    have."""
    return _id(f"doi:{doi}")


def _literal(text: str) -> str:
    """Text from a record as Markdown that lays out as written: HTML's specials as entities, Markdown's inline specials
    escaped, and each line break a <br>, so text of several paragraphs stays on one line of the Markdown, inside its
    list item or table cell, and nothing in it is read as a tag, emphasis, code or a link."""
    escaped = re.sub(r"([\\`*_\[\]])", r"\\\1", escape(text, quote=False))
    return "<br>".join(escaped.splitlines())


def _named(names: list[str]) -> str:
    """Names from a record, such as ExoFOP's listings, as a list in words."""
    return _words([_literal(name) for name in names])


def _quote(text: str) -> str:
    """Quoted text in quotation marks, which mark it apart from the paper's own words, laid out word for word (decision
    0037)."""
    return f'"{_literal(_scrub(text))}"'


def _stop(sentence: str) -> str:
    """A sentence with its full stop, unless it ends on a quote whose own text already ends one."""
    return sentence if re.search(r'[.?!]"$', sentence) else f"{sentence}."


def _beside(notes: list[dict]) -> str:
    """The notes added on a quoted finding under decision 0037, each nested under the finding after its quoted lines.
    Python-Markdown nests a list only at four spaces."""
    return "".join(
        f"\n    - **Note ({_date(n['date'])}):** {_literal(_scrub(n['text']))}" for n in notes
    )


def _claims(record: Path) -> dict | None:
    """claims.json, the record's sort under decision 0042, or None when the record holds none."""
    path = record / "claims.json"
    return json.loads(path.read_text()) if path.is_file() else None


def _excepted(record: Path) -> list[dict]:
    """The later listings decision 0042 excepts for the record."""
    found = _claims(record)
    return [] if found is None else found["excepted"]


def _upcoming(record: Path) -> str:
    """The sectors tess-point placed the star in at the record's vetting run, as a sentence; none when the run did
    not record them."""
    upcoming = json.loads((record / "checks.json").read_text())["upcoming_sectors"]
    if upcoming is None:
        return ""
    made = json.loads((record / "provenance-checks.json").read_text())
    version = calls.version(record)
    run = "the vetting run" if version is None else f"the vetting run of version r{version}"
    when = f"As of {run} ({_date(made['started_at'])}), tess-point (Burke et al. 2020) predicted"
    if not upcoming:
        return f" {when} no further TESS sectors for the star."
    return f" {when} that TESS would observe the star in {prereg._sectors_words(upcoming)}."


def _same_fit(made: dict, recorded: dict) -> None:
    """Refuses unless a reproduced fit's summary is the record's: each parameter's median and its distances to the
    16th and 84th percentiles, and the acceptance."""
    pairs = [
        (f"{name} {part}", made[name][part], recorded[name][part])
        for name in NAMES
        for part in ("median", "minus", "plus")
    ]
    for what, value, kept in [*pairs, ("acceptance", made["acceptance"], recorded["acceptance"])]:
        if not math.isclose(value, kept, rel_tol=1e-9):
            raise SystemExit(
                f"the reproduced density-prior fit gives {what} {value!r}, not the record's {kept!r}: the paper's "
                "depth and duration need the record's posterior"
            )


def _depths(samples: np.ndarray) -> np.ndarray:
    """Each sample's transit depth at mid-transit: the transit model's, with the sample's limb darkening and no
    exposure smearing, which belongs to a cadence and not to the transit."""
    out = np.empty(len(samples))
    for i, (t0, period, rp_rs, b, log_rho, q1, q2) in enumerate(samples):
        # Kipping's q1 and q2 as fit_transit turns them into quadratic coefficients.
        u1, u2 = 2.0 * np.sqrt(q1) * q2, np.sqrt(q1) * (1.0 - 2.0 * q2)
        a_rs = a_rs_from_density(10.0**log_rho, period)
        out[i] = 1.0 - light_curve([t0], [0.0], t0, period, rp_rs, a_rs, b, u1, u2)[0]
    return out


def _known(value) -> bool:
    """An error the record keeps: a positive number, not a null or a NaN."""
    return value is not None and math.isfinite(value) and value > 0


def reproduce(record: Path) -> dict[str, np.ndarray] | None:
    """The record's density-prior fit, reproduced by vet's own fit from the light curve its vetting run read, the
    criteria that run recorded and their seed, with each sample's depth at mid-transit, full duration and radius; None
    when the record has no such fit. Refuses unless the reproduction gives the record's summary of the fit."""
    checks = json.loads((record / "checks.json").read_text())
    if checks["fit_prior"] is None:
        return None
    made = json.loads((record / "provenance-checks.json").read_text())
    version = checks["criteria_version"]
    (search,) = {Path(c["file"]).stem for c in made["criteria"]} - {version}
    crit_search = _criteria(record, "provenance-checks.json", search).values
    crit_vet = _criteria(record, "provenance-checks.json", version).values
    eph = Ephemeris(**checks["ephemeris"])
    lc = LightCurve.load(_light_curve(record)[1])
    # vet.prepare's light curve, rebuilt from the record: the catalogues its masks came from are no part of it, so the
    # rows it masked are read back from checks.json. The summary check below holds the rebuild to the fit.
    good = good_timestamps(lc) if crit_vet["timing"]["exclude_timing_suspect"] else lc
    flat = detrend(good, crit_search["detrend"], [Ephemeris(**m) for m in checks["masked"]])
    families = crit_vet["families"]
    fit_lc = split(flat, families)[families["fit"]]
    cfg = crit_vet["fit"]
    prior = vet.density_prior(checks["star"], crit_vet["density"]["default_log_rho_error"])
    fit = vet.fit_transit(fit_lc, eph, cfg, rho_prior=prior, seed=cfg["seed"])
    _same_fit(fit.summary(), checks["fit_prior"])
    # The TIC radius enters each sample's Rp as a draw from its value and error; a star the TIC gives no error for
    # keeps its value, and Rp the spread of Rp/R⋆ alone, as the record's fit summary has it. The draws take a seed
    # sequence of their own from the criteria's seed: the seed alone is the stream fit_transit placed its walkers with.
    star = checks["star"]
    rad, e_rad = (np.nan if star.get(k) is None else float(star[k]) for k in ("rad", "e_rad"))
    rng = np.random.default_rng([cfg["seed"], 1])
    radii = rng.normal(rad, e_rad if _known(e_rad) else 0.0, len(fit.samples))
    return {
        "names": np.array(NAMES),
        "samples": fit.samples,
        "depth": _depths(fit.samples),
        "t14_days": vetting.fit_durations(fit),
        "rad_rsun": radii,
        "rp_rearth": fit.column("rp_rs") * radii * R_EARTH_PER_R_SUN,
    }


def _percentiles(values: np.ndarray) -> dict:
    p16, median, p84 = np.percentile(values, [16, 50, 84])
    return {"median": median, "minus": median - p16, "plus": p84 - median}


def _parameters(found: dict) -> str:
    """Table 1, with its caption above and its note below (AAS)."""
    rows = [
        ["Period, <i>P</i> (d)", found["period_pm"]],
        ["Mid-transit time, <i>T</i><sub>0</sub> (BTJD)", found["t0_pm"]],
        ["Total duration, <i>T</i><sub>14</sub> (h)", found["duration_pm"]],
        ["Depth at mid-transit (ppm)", found["depth_pm"]],
        ["Planet-to-star radius ratio, <i>R</i><sub>p</sub>/<i>R</i><sub>⋆</sub>", found["rp_rs"]],
        ["Radius, <i>R</i><sub>p</sub> (R⊕)", found["rp_pm"]],
        ["Impact parameter, <i>b</i>", found["b"]],
        ["Scaled semi-major axis, <i>a</i>/<i>R</i><sub>⋆</sub>", found["a_rs"]],
    ]
    return (
        f"**Table 1.** Transit parameters of TIC {found['tic']} from the density-prior fit\n\n"
        + _table(["Parameter", "Value"], rows)
        + "\n\n*Note.* The <i>P</i> and <i>T</i><sub>0</sub> uncertainties are posterior standard deviations. For the "
        "other parameters, the value is the posterior median with its differences from the 16th and 84th percentiles. "
        "<i>T</i><sub>14</sub> runs from first to fourth contact, and the depth is the transit model's at mid-transit. "
        "Both come from the density-prior fit's posterior, which this paper's run reproduced from the record's light "
        "curve, criteria and seed and checked against the record's summary of the fit. <i>R</i><sub>p</sub> is "
        f"<i>R</i><sub>p</sub>/<i>R</i><sub>⋆</sub> times the TIC radius{found['rp_from']} (Section 3). BTJD = "
        f"BJD<sub>TDB</sub> {MINUS} 2457000."
    )


def _with_error(value, error, fmt: str) -> str | None:
    """A TIC value with the TIC's error when the record keeps one."""
    shown = _number(value, fmt)
    return f"{shown} ± {error:{fmt}}" if shown is not None and _known(error) else shown


def _star(checks: dict, posterior: dict | None) -> dict:
    star, prior = checks["star"], checks["fit_prior"]
    with_rad_error = _known(star.get("e_rad"))
    found = {
        "tic": str(checks["tic"]),
        "tmag": _number(star["tmag"], ".2f"),
        "teff": _with_error(star["teff"], star.get("e_teff"), ".0f"),
        "radius_sun": _with_error(star["rad"], star.get("e_rad"), ".2f"),
        "radius_error": "" if with_rad_error else " The TIC gives no error for the star's radius.",
        # The search's box, which the checks, the neighbour check and the figures use; Section 4 alone gives it.
        "box_duration_h": _number(checks["ephemeris"]["duration"] * 24, ".2f"),
        "box_depth_ppm": _ppm(checks["ephemeris"]["depth"]),
    }
    if prior is None:
        return found
    fit = prior["ephemeris"]
    found |= {
        "period_pm": f"{fit['period']['median']:.6f} ± {fit['period']['sd']:.6f}",
        "period_short": _number(fit["period"]["median"], ".1f"),
        "t0_pm": f"{fit['t0']['median']:.4f} ± {fit['t0']['sd']:.4f}",
        "duration_pm": _spread(_percentiles(posterior["t14_days"] * 24), ".2f"),
        "depth_pm": _spread(_percentiles(posterior["depth"] * 1e6), ".0f"),
        "rp_rs": _spread(prior["rp_rs"], ".4f"),
        "b": _spread(prior["b"], ".2f"),
        "a_rs": _spread(prior["a_rs"], ".2f"),
        "rp_from": ", drawn for each sample from its value and error" if with_rad_error else "",
    }
    # The radius needs the TIC's stellar radius, which the record's fit summary says it had; a paper without it leaves
    # its placeholders unfilled.
    if prior["rp_rearth"] is not None:
        found["rp_pm"] = _spread(_percentiles(posterior["rp_rearth"]), ".2f")
        found["parameters"] = _parameters(found)
    return found


def _changed(version: Path) -> str:
    """What a new vetting's light curve changed, from its merge record (decision 0041)."""
    tic = json.loads((version / "checks.json").read_text())["tic"]
    merged = json.loads((version / "merge.json").read_text())[str(tic)]["sectors"]
    rows = sorted(merged.items(), key=lambda item: int(item[0]))
    said = []
    added = [f"Sector {s} ({x['fresh']['provenance']})" for s, x in rows if x["status"] == "added"]
    if added:
        said.append(f"{_words(added)} added")
    said += [
        f"Sector {s}'s timing-suspect delivery replaced by a newer one"
        for s, x in rows
        if x["status"] == "redelivered"
    ]
    said += [
        f"Sector {s}'s {x['base']['provenance']} light curve replaced by {x['fresh']['provenance']}'s"
        for s, x in rows
        if x["status"] == "upgraded"
    ]
    if not said:
        return "a new vetting on the same light curve"
    return f"a new vetting on a light curve with {_words(said)}"


def _history(record: Path) -> str:
    """Each published record of the signal up to `record`: our call on an earlier one, its reason quoted, and what
    each new vetting's light curve changed."""
    versions = _versions(record)
    if len(versions) == 1:
        return "This paper reports the signal's only record."
    said = [f"The signal has {_count(len(versions), 'record')}."]
    for r in versions[:-1]:
        n = calls.version(r)
        call = calls.load(r / "call.toml")
        at = "its first record" if n is None else f"version r{n}, {_changed(r)},"
        said.append(
            _stop(
                f"We {call['outcome']} the signal at {at} on {_date(call['date'])}, giving the reason "
                f"{_quote(call['reasons'])}"
            )
        )
        if call["deciding_evidence"]:
            said.append(
                _stop(
                    "The call named the evidence that would decide the signal: "
                    f"{_quote(call['deciding_evidence'])}"
                )
            )
    n = calls.version(record)
    said.append(
        f"This paper reports the {ORDINALS.get(n, 'latest')} record, version r{n}, {_changed(record)}."
    )
    return " ".join(said)


def _matched(check: dict) -> list[str]:
    """The listings a novelty check matched to the signal, by name."""
    return [m["name"] for m in check["evidence"].get("matches") or []]


def _novelty_said(check: dict) -> str:
    """A novelty check's outcome with what it matched, after a listing is set aside; its reason, quoted, where its
    evidence lists no match."""
    matched = _matched(check)
    if check["outcome"] == "pass":
        return "no other catalogued object matches the signal, and the novelty check passes"
    if matched:
        return (
            f"the novelty check {IS[check['outcome']]} because {_named(matched)} "
            f"{'matches' if len(matched) == 1 else 'match'} the signal"
        )
    return f"the novelty check {IS[check['outcome']]}, for the reason {_quote(check['reason'])}"


def _novelty_against(check: dict) -> str:
    """The vetting run's own novelty check, against the catalogues it used."""
    head = "Against the catalogues used in the vetting run, the novelty check"
    matched = _matched(check)
    if check["outcome"] == "pass":
        return f"{head} passes: no known object matches the signal."
    if matched:
        return (
            f"{head} {IS[check['outcome']]} because {_named(matched)} "
            f"{'matches' if len(matched) == 1 else 'match'} the signal."
        )
    return _stop(f"{head} {IS[check['outcome']]}, for the reason {_quote(check['reason'])}")


def _novelty(record: Path, checks: dict, call: dict) -> str:
    """What Table 2's novelty row leaves out: a rerun under decision 0042 and a promotion under 0013."""
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    judged = calls.novelty(record, checks)
    excepted = _excepted(record)
    said = []
    if excepted:
        # The paragraph before names each listing and when ExoFOP first listed it; this one only sets them aside.
        matched = len(excepted) == 1 and excepted[0]["name"] in _matched(own)
        aside = f"the {excepted[0]['source']}" if matched else _named([r["name"] for r in excepted])
        said.append(
            f"{_novelty_against(own)} "
            + _stop(f"With {aside} set aside under DR 0042, {_novelty_said(judged)}")
        )
    if judged["outcome"] != "pass":
        said.append(
            _stop(f"T{_novelty_said(judged)[1:]}")
            + " The rows at the signal's period are SPOC threshold-crossing events or ExoMiner rows that never became "
            "TOIs. DR 0013 lets the call promote such a signal, and we promoted this one. "
            + _stop(f"The call gives the reason {_quote(call['promotion'])}")
        )
    return "\n\n".join(said)


def _modshift(checks: dict) -> str:
    m = checks["modshift"]
    test = "ModShift, the model-shift uniqueness test (Rowe et al. 2015; Coughlin et al. 2016)"
    if m is None:
        return (
            f"{test}, which LEO-Vetter runs during triage, has no result in the record "
            f"({_quote(checks['triage_reason'])})."
        )
    depth = None if m["dep_sec"] is None else m["dep_sec"] * 1e6
    return (
        f"{test}, searches for a secondary eclipse at any phase, and LEO-Vetter runs it during triage. The most "
        f"significant secondary event is at phase {_f(m['phs_sec'], '.3g')}, with a depth of {_f(depth, '.0f')} ppm "
        f"and a significance of {_f(m['sig_sec'], '.3g')}σ. The primary event has a significance of "
        f"{_f(m['sig_pri'], '.3g')}σ, and ModShift's red-noise factor, F<sub>red</sub>, is {_f(m['Fred'], '.3g')}."
    )


def _eccentric(checks: dict) -> str:
    m = checks["modshift"]
    there = (
        "In an eccentric orbit it can fall at another phase, which only ModShift searches. ModShift's most significant "
        f"secondary event is {_f(m['sig_sec'], '.3g')}σ."
        if m is not None
        else "In an eccentric orbit it can fall at another phase, and the record holds no ModShift result."
    )
    return (
        "The secondary-eclipse check searches only at phase 0.5, where an eclipsing binary's secondary eclipse falls "
        f"if the orbit is circular. {there}"
    )


def _red_noise(checks: dict) -> str:
    rows = sorted(checks["red_noise"].items(), key=lambda item: int(item[0]))
    measured = [f"{r['beta']:.2f} in Sector {s}" for s, r in rows if "note" not in r]
    unmeasured = [int(s) for s, r in rows if "note" in r]
    said = [
        "The red-noise factor β scales each sector's depth errors and is measured from the residuals binned at the "
        "timescale of the transit core (Pont et al. 2006; DR 0006)."
    ]
    if measured:
        said.append(f"The factor is {_words(measured)}.")
    if unmeasured:
        them, their = ("it", "its") if len(unmeasured) == 1 else ("them", "their")
        said.append(
            f"{prereg._sectors_words(unmeasured)} had too few binned points to measure β, so β is set to 1 for {them} "
            f"and {their} depth errors assume white noise."
        )
    return " ".join(said)


def _tdepth_zero(evidence: dict, hosts: list[dict], limit: float) -> str:
    """The neighbour check's possible hosts TRICERATOPS gave zero depth: it computed no scenario for them (decision
    0026, Ruling M), and any of them inside the pixel check's reach."""
    zero = evidence["hosts_tdepth_zero"]
    if not zero:
        return ""
    one = len(zero) == 1
    if len(zero) == len(hosts):
        which = (
            "the neighbour check's one possible host"
            if one
            else "both of the neighbour check's possible hosts"
            if len(hosts) == 2
            else f"all {_spell(len(hosts))} of the neighbour check's possible hosts"
        )
    else:
        which = (
            f"{_spell(len(zero))} of the neighbour check's {_count(len(hosts), 'possible host')}"
        )
    star, it, its = ("that star", "it", "its") if one else ("those stars", "them", "their")
    said = (
        f" The apertures take in too little of the light of {which} to produce the transit, so TRICERATOPS assigned "
        f"{it} a transit depth of zero and computed no scenario for {it} (DR 0026). Whether {star} can be excluded "
        f"therefore depends on how much of {its} light TRICERATOPS places in the apertures and on the pixel check, "
        f"and no false-positive probability covers {it}."
    )
    inside = [
        h
        for h in hosts
        if h.get("source_id") in zero and h["sep_arcsec"] is not None and h["sep_arcsec"] < limit
    ]
    if inside:
        if one:
            lies = "That star lies"
        elif len(inside) == len(zero):
            lies = "Both of them lie" if len(zero) == 2 else f"All {_spell(len(zero))} of them lie"
        else:
            lies = f"{_spell(len(inside)).capitalize()} of them {'lies' if len(inside) == 1 else 'lie'}"
        said += f" {lies} within {limit:g}″ of the target, closer than the pixel check can resolve (Section 6.2)."
    return said


def _validated(record: Path, version: str, triceratops: dict) -> str:
    """Whether Giacalone et al.'s "validated planet" label applies, by decision 0026's conditions."""
    limit = _criteria(record, "provenance-triceratops.json", version)["triceratops"][
        "fpp_validated"
    ]
    e = triceratops["evidence"]
    said = (
        'Giacalone et al. also define a "validated planet" label, which DR 0026 applies only with an FPP under '
        f"{limit:g}, a high-resolution contrast curve and 2-minute data."
    )
    if e["validated_label"]:
        return f"{said} These runs meet those conditions, but this paper still calls the signal a planet candidate."
    lacking = [
        (a, no)
        for a, no, met in (
            (f"an FPP under {limit:g}", f"no FPP under {limit:g}", e["fpp_mean"] < limit),
            ("a contrast curve", "no contrast curve", bool(triceratops["contrast"])),
            ("2-minute data", "no 2-minute data", e["exposure_s"] == TWO_MINUTES_S),
        )
        if not met
    ]
    if len(lacking) == 2:
        had = f"neither {lacking[0][0]} nor {lacking[1][0]}"
    else:
        had = _words([no for _, no in lacking])
    return f"{said} These runs had {had}, so the label does not apply."


def _offsets(pixel: dict, suspect: set[int]) -> dict:
    """Each sector's centroid offset, and the sector the outcome comes from: the pixel check judges the best-quality
    sector's offset, and the row holding that offset is its sector (as the dossier finds it)."""
    sectors = sorted(pixel["evidence"]["sectors"], key=lambda s: s["sector"])
    offsets = (
        "The offsets were "
        + _words(
            [
                f"{_f(s['offset_arcsec'], '.1f')}″ in Sector {s['sector']} (quality {_f(s['quality'], '.2f')})"
                for s in sectors
            ]
        )
        + "."
    )
    judged_offset = pixel["evidence"]["offset_qual_arcsec"]
    judged = [
        s["sector"]
        for s in sectors
        if judged_offset is not None and s["offset_arcsec"] == judged_offset
    ]
    outcome = pixel["outcome"]
    if len(judged) == 1:
        n = judged[0]
        said = f"Sector {n} has the best quality, so the check's {outcome} is based on its offset"
        said += (
            f", even though the vetting run left Sector {n} out because its timestamps are suspect."
            if n in suspect
            else "."
        )
    else:
        said = f"The check's {outcome} is based on the best-quality offset, which no single sector above reports."
    others = sorted(
        s["sector"] for s in sectors if s["sector"] in suspect and s["sector"] not in judged
    )
    if others:
        said += (
            f" The vetting run left {prereg._sectors_words(others)} out because "
            f"{'its timestamps are' if len(others) == 1 else 'their timestamps are'} suspect."
        )
    return {"offsets": offsets, "rests_on": said}


def _blends(hosts: list[dict], limit: float, zero: list) -> str:
    """The possible hosts neither the pixel check nor TRICERATOPS can exclude. The paper gives their count, not their
    Gaia values."""
    if not hosts:
        return "The neighbour check found no possible hosts."
    inside = [h for h in hosts if h["sep_arcsec"] is not None and h["sep_arcsec"] < limit]
    within = f"within {limit:g}″ of the target, too close for the pixel check to separate"
    two = len(hosts) == 2
    if len(hosts) == 1:
        said = (
            f"The one possible host from the neighbour check lies {within}"
            if inside
            else f"The one possible host from the neighbour check does not lie within {limit:g}″ of the target"
        )
        said += ", and TRICERATOPS computed no scenario for it." if zero else "."
    else:
        if not inside:
            said = (
                f"{'Neither' if two else 'None'} of the neighbour check's {_spell(len(hosts))} possible hosts lies "
                f"within {limit:g}″ of the target."
            )
        elif len(inside) == len(hosts):
            every = "Both" if two else f"All {_spell(len(hosts))}"
            said = f"{every} of the neighbour check's possible hosts lie {within}."
        else:
            lie = "lies" if len(inside) == 1 else "lie"
            said = (
                f"{_spell(len(inside)).capitalize()} of the neighbour check's {_spell(len(hosts))} possible hosts "
                f"{lie} {within}."
            )
        if zero:
            every = "either of them" if two else "any of them"
            on = every if len(zero) == len(hosts) else f"{_spell(len(zero))} of them"
            said += f" TRICERATOPS computed no scenario for {on}."
    if inside or zero:
        them = "that star" if len(hosts) == 1 else "those stars"
        said += f" Photometry that resolves the stars near the target could rule {them} out."
    return said


def _companions(triceratops: dict, exofop: dict) -> str:
    contrast = triceratops["contrast"]
    if contrast:
        return (
            "TRICERATOPS evaluated the unresolved-companion and background-star scenarios from its priors, "
            f"constrained by {_count(len(contrast), 'high-resolution contrast curve')} of the star from ExoFOP."
        )
    said = (
        "With no high-resolution contrast curve as input, TRICERATOPS evaluated the unresolved-companion and "
        "background-star scenarios from its priors alone."
    )
    if exofop["imaging"]:
        said += (
            f" ExoFOP lists {_count(len(exofop['imaging']), 'high-resolution imaging observation')} of the star, "
            "which TRICERATOPS did not use."
        )
    return said


def _listing(raw: str, kind: str) -> str:
    """An ExoFOP TOI or CTOI by the name the novelty check gives it (catalogs.py): "TOI 266.01" is "TOI-266.01" and "TIC
    164767175.03" is "CTOI-164767175.03"."""
    if kind == "TOI":
        return re.sub(r"^TOI[ -]?", "TOI-", raw.strip())
    return re.sub(r"^(TIC|CTOI)[ -]?", "CTOI-", raw.strip())


def _listed(rows: list[dict], kind: str, field: str, disposition: str) -> str:
    """ExoFOP's TOIs or CTOIs on the star, counted and named, each with its disposition."""
    if not rows:
        return _count(0, kind)
    named = [
        f"{_literal(_listing(r[field], kind))}, disposition {_literal(r.get(disposition) or 'none')}"
        if len(rows) == 1
        else f"{_literal(_listing(r[field], kind))} with disposition "
        f"{_literal(r.get(disposition) or 'none')}"
        for r in rows
    ]
    return f"{_count(len(rows), kind)} ({_words(named)})"


def _exofop(exofop: dict) -> str:
    """What ExoFOP lists on the star besides the planet-parameter rows: TOIs, CTOIs, confirmed planets and imaging."""
    if exofop["status"] != "ok":
        return f"ExoFOP's records for the star could not be read ({_quote(exofop['error'])})."
    planets = [p.strip() for p in (exofop["confirmed_planets"] or "").split(",") if p.strip()]
    parts = [
        _listed(exofop["tois"], "TOI", "toi", "disp_tfop"),
        _listed(exofop["ctois"], "CTOI", "ctoi", "cdisp"),
        f"{_count(len(planets), 'confirmed planet')} ({_named(planets)})"
        if planets
        else _count(0, "confirmed planet"),
        _count(len(exofop["imaging"]), "high-resolution imaging observation"),
    ]
    return f"ExoFOP lists {_words(parts)} for the star."


def _vetting(record: Path, checks: dict, call: dict, literature: dict) -> dict:
    sources, vetted = checks["sources"], sorted(s for f in checks["families"].values() for s in f)
    dropped = checks["dropped_suspect"]
    version = checks["criteria_version"]
    vet = _criteria(record, "provenance-checks.json", version)
    pixel = calls.pixels(record, checks)
    triceratops = json.loads((record / "triceratops.json").read_text())
    tric = triceratops["evidence"]
    hosts = checks["neighbours"]["evidence"]["possible_hosts"]
    novelty = _novelty(record, checks, call)
    rows = [[c["check"], c["outcome"], c["reason"]] for c in checks["checks"]]
    rows += [
        ["neighbours", checks["neighbours"]["outcome"], checks["neighbours"]["reason"]],
        ["pixels", pixel["outcome"], pixel["reason"]],
        ["triceratops", triceratops["outcome"], triceratops["reason"]],
        ["literature", literature["outcome"], literature["reason"]],
    ]
    # Only a listing the novelty check matched is at the signal's period or a harmonic of it: decision 0042 excepts
    # later ones at any period.
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    at_period = [r["name"] for r in _excepted(record) if r["name"] in _matched(own)]
    second = checks["signal"]["kind"] == "second"
    exofop = literature["search"]["exofop"]
    limit = pixel["max_offset_arcsec"]
    holdout = next(c for c in checks["checks"] if c["check"] == "holdout")
    seasons = holdout["evidence"]["seasons"]
    tested = [s for s in seasons if s["status"] in ("predicted", "missed")]
    predicted = sum(s["status"] == "predicted" for s in tested)
    untested = "".join(
        f" The season from BTJD {s['start']:.1f} to {s['end']:.1f} was not testable"
        + (
            f" ({_quote(s['reason'])})."
            if s.get("reason")
            else f", because {UNTESTED.get(s['status'], s['status'])}."
        )
        for s in seasons
        if s not in tested
    )
    judged, excepted = calls.novelty(record, checks), _excepted(record)
    runs = len(tric["fpp"])
    fpp = _mean_sd(tric["fpp_mean"], tric["fpp_sd"], runs)
    nfpp = _mean_sd(tric["nfpp_mean"], tric["nfpp_sd"], runs)
    return {
        "vetting_run": json.loads((record / "provenance-checks.json").read_text())["run_id"],
        "criteria_version": version,
        "season_gap_days": f"{vet['holdout']['season_gap_days']:g}",
        "core": f"{100 * vet['depth']['core_fraction']:g}%",
        "min_sigma": f"{vet['holdout']['min_sigma']:g}",
        "max_tension": f"{vet['holdout']['max_depth_tension']:g}",
        "bar_promotion": " For a SPOC threshold-crossing event that never became a TOI, a promotion in the call can "
        "replace the novelty check's pass (DR 0013)."
        if second
        else "",
        "vetted_products": _words(
            sorted(
                {
                    PRODUCT_NAMES.get(p, p)
                    for p in (prereg.PRODUCTS[sources[str(s)]["provenance"]] for s in vetted)
                }
            )
        ),
        "vetted_sectors": prereg._sectors_words(vetted),
        "suspect": f" {prereg._sectors_words(dropped)} "
        + ("was left out because its" if len(dropped) == 1 else "were left out because their")
        + " timestamps are suspect (DR 0022)."
        if dropped
        else "",
        "checks": _checks_table(rows, own, judged, excepted),
        "abstract_checks": _abstract_checks(rows, own, judged, excepted),
        "novelty": novelty,
        "modshift": _modshift(checks),
        "eccentric": _eccentric(checks),
        "red_noise": _red_noise(checks),
        "hosts": f"The neighbour check found {_count(len(hosts), 'possible host')}."
        + (
            " The dataset's `neighbours.csv` gives the eclipse depth "
            f"{'that star' if len(hosts) == 1 else 'each'} would need to produce the transit."
            if hosts
            else ""
        ),
        "tdepth_zero": _tdepth_zero(tric, hosts, limit),
        "tric_data": f"{prereg._sectors_words(tric['sectors'])} at {tric['exposure_s']:g}-s exposures"
        + (", folded and binned in phase" if tric["bin_phase"] else ""),
        "fpp_pm": fpp,
        "nfpp_pm": nfpp,
        "tric_probabilities": (
            f"The false-positive probability (FPP) is {fpp} and the nearby false-positive probability (NFPP) is {nfpp}."
            if runs < 2
            else f"Over those runs, the false-positive probability (FPP) is {fpp} and the nearby false-positive "
            f"probability (NFPP) is {nfpp} (mean ± standard deviation)."
        ),
        "validated": _validated(record, version, triceratops),
        "pixel_check": "the second list's, run as triage runs it" if second else "triage's",
        "max_offset": f"{limit:g}",
        **_offsets(pixel, set(dropped)),
        "blends": _blends(hosts, limit, tric["hosts_tdepth_zero"]),
        # results/README.md leaves a bare Gaia DR3 source id under CC BY 4.0; the paper leaves it out anyway, so its own
        # text holds nothing from Gaia.
        "names": _named([n for n in literature["search"]["names"] if not n.startswith("Gaia ")]),
        "papers": _count(len(literature["evidence"]["hits"]), "paper"),
        "exofop": _exofop(exofop),
        "exofop_rows": "None of ExoFOP's planet-parameter rows for the star matches the signal's period or a "
        "harmonic of it."
        if not at_period
        else f"Apart from {_words(at_period)}, none of ExoFOP's planet-parameter rows for the star matches the "
        "signal's period or a harmonic of it.",
        "tric_times": {1: "once", 2: "twice"}.get(runs, f"{_spell(runs)} times"),
        "companions": _companions(triceratops, exofop),
        "holdout": f"For this signal {_seasons(len(seasons), len(tested), predicted)}, so the check "
        f"{WAS[holdout['outcome']]}." + untested,
    }


def _checks_table(rows: list[list], own: dict, judged: dict, excepted: list[dict]) -> str:
    """Table 2, the record's outcomes and reasons verbatim, with a lettered footnote on a novelty outcome that is not
    a pass and that Section 6.4 sets aside or the call's promotion replaces."""
    note = []
    if own["outcome"] != "pass" and (excepted or judged["outcome"] != "pass"):
        if excepted:
            names = [r["name"] for r in excepted]
            note.append(
                f"ExoFOP first listed {_named(names)} after we made the signal public, so DR 0042 sets "
                f"{'it' if len(names) == 1 else 'them'} aside."
            )
        if judged["outcome"] != "pass":
            note.append("The call promotes the signal past this check under DR 0013.")
    cells = [
        [
            f"{CHECKS[name]} (`{name}`)",
            f"{outcome}<sup>a</sup>" if name == "novelty" and note else outcome,
            _literal(reason),
        ]
        for name, outcome, reason in rows
    ]
    footnote = f" <sup>a</sup> {' '.join(note)} See Section 6.4." if note else ""
    return (
        "**Table 2.** Vetting checks\n\n"
        + _table(["Check", "Outcome", "Reason, as the record gives it"], cells)
        + f"\n\n*Note.* Outcomes and reasons are the record's, verbatim.{footnote}"
    )


def _abstract_checks(rows: list[list], own: dict, judged: dict, excepted: list[dict]) -> str:
    """The Abstract's word on Table 2: every check passed, or which did not and why the call stands."""
    failing = [(name, outcome) for name, outcome, _ in rows if outcome != "pass"]
    if not failing:
        return "Every vetting check passed."
    parts = []
    for name, outcome in failing:
        if name == "novelty":
            matched = _matched(own)
            parts.append(
                "the comparison with known objects, which "
                + (f"matched {_named(matched)}" if matched else WAS[outcome])
            )
        else:
            # Table 2's wording for the check, lowercased unless it opens on a name.
            label = CHECKS[name]
            if label.split()[0] not in ("Gaia", "TRICERATOPS's"):
                label = label[0].lower() + label[1:]
            parts.append(f"the check of {label}, which {WAS[outcome]}")
    said = f"Every vetting check passed except {_words(parts)}."
    if own["outcome"] != "pass" and excepted:
        named = [r for r in excepted if r["name"] in _matched(own)]
        listed = named or excepted
        one = len(listed) == 1
        # The sentence before names a matched listing; one it doesn't name is named here.
        which = (
            f"that {listed[0]['source']}" if one and named else _named([r["name"] for r in listed])
        )
        said += (
            f" ExoFOP listed {which} only after we made the signal public, so "
            f"{'it does not count as a known object' if one else 'they do not count as known objects'}."
        )
    if judged["outcome"] != "pass":
        said += (
            " We promoted the signal past that check, as our rules allow for a SPOC threshold-crossing event that "
            "never became a TOI."
        )
    return said


def _seasons(n: int, testable: int, predicted: int) -> str:
    """How many of the signal's seasons the held-out check could test, and how many it predicted, as a clause."""
    if n == 1:
        if not testable:
            return "its one season was not testable"
        return f"its one season was testable and was{'' if predicted else ' not'} predicted"
    if not testable:
        return f"{'neither' if n == 2 else 'none'} of its {_spell(n)} seasons was testable"
    if testable == n:
        head = "both seasons were testable" if n == 2 else f"all {_spell(n)} seasons were testable"
    else:
        head = f"{_spell(testable)} of its {_spell(n)} seasons {'was' if testable == 1 else 'were'} testable"
    if testable == 1:
        tail = f"it was{'' if predicted else ' not'} predicted"
    elif predicted == testable:
        tail = "both were predicted" if testable == 2 else "all were predicted"
    elif not predicted:
        tail = "neither was predicted" if testable == 2 else "none was predicted"
    else:
        tail = f"{_spell(predicted)} {'was' if predicted == 1 else 'were'} predicted"
    return f"{head} and {tail}"


def _label(finding: dict, confirmed: list[str]) -> str:
    """A finding's id, the question it concerns, its rating and what its refuters did."""
    head = f"{_literal(finding['id'])}, on {QUESTIONS[finding['lens']]}."
    if finding["rating"] == "note":
        return f"{head} Rated note."
    n = len(finding["refuters"])
    if finding["id"] not in confirmed:
        k = sum(v["refuted"] for v in finding["refuters"])
        if n == 1:
            who = "its one refuter"
        elif k == n:
            who = "both of its refuters" if n == 2 else f"all {_spell(n)} of its refuters"
        else:
            who = f"{_spell(k)} of its {_spell(n)} refuters"
        said = f"{who} disproved it"
    # Upheld only because nothing tested it, as the dossier says: the reader should not take it for tested.
    elif n == 0:
        said = "no refuter tested it, so it counts as upheld"
    elif n == 1:
        said = "its one refuter did not disprove it"
    elif n == 2:
        said = "neither of its two refuters disproved it"
    else:
        said = f"none of its {_spell(n)} refuters disproved it"
    return f"{head} Rated {finding['rating']}; {said}."


def _fates(findings: list[dict], confirmed: list[str]) -> str:
    """How many of the review's findings were upheld (the records' `confirmed`), refuted or notes, by rating."""
    n = len(findings)
    if not n:
        return "The review raised no findings."
    counts = Counter(
        ("note", "note")
        if f["rating"] == "note"
        else ("upheld" if f["id"] in confirmed else "refuted", f["rating"])
        for f in findings
    )
    if len(counts) == 1:
        (fate, rating), _ = counts.popitem()
        every = (
            "The review's one finding"
            if n == 1
            else "Both of the review's findings"
            if n == 2
            else f"All {_spell(n)} of the review's findings"
        )
        if fate == "note":
            return f"{every} {'was a note' if n == 1 else 'were notes'}."
        return f"{every}, rated {rating}, {'was' if n == 1 else 'were'} {fate}."

    def told(k: int, rating: str, fate: str) -> str:
        return f"{_spell(k)} rated {rating} {'was' if k == 1 else 'were'} {fate}"

    said = [
        told(k, rating, fate)
        for fate in ("upheld", "refuted")
        for rating in ("kill", "hold")
        if (k := counts[fate, rating])
    ]
    if k := counts["note", "note"]:
        said.append("one was a note" if k == 1 else f"{_spell(k)} were notes")
    return f"Of the review's {_count(n, 'finding')}, {', '.join(said[:-1])}, and {said[-1]}."


def _flagged(review: dict, literature: dict) -> str:
    """The papers the review flagged, each by its title and id where the literature search found it."""
    flagged = review["hits_flagged"]
    if not flagged:
        return "The review flagged no papers for us to read."
    hits = literature["evidence"]["hits"]

    def paper(ident: str) -> str:
        hit = next((h for h in hits if ident in (h["arxiv"], h["doi"])), None)
        if hit is None:
            return _literal(ident)
        found = _literal(_paper_id(hit))
        return f"{_quote(hit['title'])} ({found})" if hit["title"] else found

    one = len(flagged) == 1
    return (
        f"The review flagged {_count(len(flagged), 'paper')} for us to read{',' if one else ':'} "
        f"{_words([paper(i) for i in flagged])}. The call records that we read {'it' if one else 'each'}."
    )


def _review(record: Path, review: dict, call: dict, literature: dict) -> dict:
    """The review's counts and its quoted findings, each with any note decision 0037 added beside it in
    review-notes.toml, and the call's answers and sentences."""
    path = record / "review-notes.toml"
    added = calls.load_notes(path, review) if path.is_file() else {}
    confirmed = calls.confirmed(review)
    findings = review["findings"]
    by_id = {f["id"]: f for f in findings}
    refuted = [f for f in findings if f["rating"] != "note" and f["id"] not in confirmed]
    noted = [f for f in findings if f["rating"] == "note"]

    def quoted(finding: dict, lines: list[str]) -> str:
        return (
            f"- {_label(finding, confirmed)}"
            + "".join(
                f"\n    - {line}" for line in [f"Finding: {_quote(finding['claim'])}", *lines]
            )
            + _beside(added.get(finding["id"], []))
        )

    answers = "\n".join(
        quoted(by_id[f], [f"Answer: {_quote(call['answers'][f])}"]) for f in confirmed
    )
    verdicts = "\n".join(
        quoted(
            f,
            [
                f"Refuter {i} {'disproved it' if v['refuted'] else 'did not disprove it'}: {_quote(v['reason'])}"
                for i, v in enumerate(f["refuters"], 1)
            ],
        )
        for f in refuted
    )
    return {
        "call_date": _date(call["date"]),
        "review_date": _date(review["date"]),
        "n_confirmed": str(len(confirmed)),
        "fates": _fates(findings, confirmed),
        "hits_read": _flagged(review, literature),
        "answers": answers or "The review upheld no findings.",
        "refuted": "Refuted findings, with each refuter's verdict:\n\n" + verdicts
        if refuted
        else "No refuter disproved any finding.",
        "notes": "Findings rated note, which need no answer:\n\n"
        + "\n".join(quoted(f, []) for f in noted)
        if noted
        else "No finding was rated note.",
        "sentences": "\n".join(
            f"- {label}: {_quote(call['sentences'][key])}" for key, label in SENTENCES.items()
        ),
    }


def _inject_run(benchmarks: Path, threshold_run: str) -> dict:
    """The published production injection-recovery run made at the search's threshold. No provenance of the record
    names it, so it is found by the threshold run it recorded; exactly one must match."""
    found = [
        made
        for made in (
            json.loads(path.read_text())
            for path in sorted(benchmarks.glob("*-benchmark-inject-*/provenance.json"))
        )
        if made.get("production") and (made.get("threshold") or {}).get("run_id") == threshold_run
    ]
    if len(found) != 1:
        raise SystemExit(
            f"{len(found)} published injection-recovery runs were made at threshold run {threshold_run}; the paper "
            "names one"
        )
    return found[0]


def _triage(row: pd.Series, made: dict, checks: dict) -> str:
    """What triage made of the signal, from its row in the triage run's signals.csv."""
    used = made["inputs"].get("triage_criteria")
    # A vetting run made before M4's deferred minors recorded no triage criteria file.
    under = f"Under triage criteria {Path(used['file']).stem}" if used else "In triage"
    if bool(row["shortlisted"]):
        return (
            f"{under}, this signal passed the novelty check, LEO-Vetter's false-alarm and flux-level tests "
            f"(LEO-Vetter's disposition: {_quote(row['leo_reason'])}) and the pixel check, and was shortlisted."
        )
    # Triage records a pixel check it never ran as inconclusive, "not run: ...".
    pixels = (
        "triage did not run its pixel check"
        if str(row["pixels_reason"]).startswith("not run")
        else f"its pixel check {WAS[row['pixels']]}"
    )
    said = (
        f"{under}, this signal's novelty check {WAS[row['novelty']]}, LEO-Vetter's tests {WAS[row['leo_flux']]} and "
        f"{pixels}, so triage did not shortlist it."
    )
    if checks["signal"]["kind"] == "second":
        said += (
            " It came to vetting on tess-hunt's second list of SPOC threshold-crossing events that never became TOIs "
            "(DR 0028)."
        )
    return said


def _found(repo: Path, checks: dict, made: dict) -> dict:
    """The search, its sample, its threshold, the injection recovery and triage, from the published runs the vetting
    run's provenance leads to."""
    results = repo / "results"
    searched = results / "benchmarks" / made["search_run"]
    search = json.loads((searched / "provenance.json").read_text())
    if len(search["criteria"]) != 1:
        raise SystemExit(f"search run {made['search_run']} names no single criteria file")
    criteria = _criteria(searched, "provenance.json", Path(search["criteria"][0]["file"]).stem)
    sample, cfg = criteria["sample"], criteria["search"]
    threshold_run = search["threshold"]["run_id"]
    threshold = json.loads((results / "benchmarks" / threshold_run / "threshold.json").read_text())
    inject = _inject_run(results / "benchmarks", threshold_run)
    if not (results / "benchmarks" / inject["run_id"] / COMPLETENESS).is_file():
        raise SystemExit(
            f"injection-recovery run {inject['run_id']} holds no {COMPLETENESS}, which the paper points to"
        )
    # Triage names a signal <tic>-<rank> and lists every signal at or above the threshold.
    rank = int(checks["signal"]["name"].rsplit("-", 1)[1])
    rows = pd.read_csv(results / "triage" / made["triage_run"] / "signals.csv")
    row = rows[(rows["tic"] == int(checks["tic"])) & (rows["rank"] == rank)]
    if len(row) != 1:
        raise SystemExit(
            f"triage run {made['triage_run']} holds {len(row)} rows for {checks['signal']['name']}, not one; the "
            "paper gives the signal's SDE and triage's steps from it"
        )
    one = row.iloc[0]
    return {
        "search_run": made["search_run"],
        "sde": _number(float(one["sde"]), ".2f"),
        "sample_stars": _spell(search["summary"]["stars"]),
        "period_min": f"{cfg['period_min_days']:g}",
        "period_max": f"{cfg['period_max_days']:g}",
        "teff_min": f"{sample['teff_min']:g}",
        "teff_max": f"{sample['teff_max']:g}",
        "tmag_max": f"{sample['tmag_max']:g}",
        "logg_min": f"{sample['logg_min']:g}",
        "logg_max": f"{sample['logg_max']:g}",
        "flame_logg_min": f"{sample['flame_logg_min']:g}",
        "min_sectors": _spell(sample["min_sectors"]),
        "recent_min": str(sample["recent_sector_min"]),
        "recent_max": str(sample["recent_sector_max"]),
        "threshold": _number(search["threshold"]["value"], ".2f"),
        "threshold_run": threshold_run,
        "null_run": threshold["null_run"],
        "n_sample": _spell(threshold["n_sample"]),
        "n_null": _spell(threshold["n_null_stars"]),
        "false_alarms": _number(threshold["expected_false_alarms"], ".2f"),
        "inject_run": inject["run_id"],
        "injections": _spell(inject["summary"]["injections"]),
        "inject_stars": _spell(inject["summary"]["stars"]),
        "completeness": COMPLETENESS,
        "triage_run": made["triage_run"],
        "triage": _triage(one, made, checks),
    }


def _deposit(record: Path, repo: Path) -> dict | None:
    """results/predictions/dois.toml's entry for the predictions package whose preregistered test the record holds,
    with the package's run id; None when it holds none."""
    path = record / "prereg.json"
    if not path.is_file():
        return None
    package = json.loads(path.read_text())["package"]
    dois = repo / DOIS
    entry = tomllib.loads(dois.read_text()).get(package) if dois.is_file() else None
    if entry is None or "doi" not in entry:
        raise SystemExit(f"{DOIS} gives no DOI for package {package}, whose test the record holds")
    return {"package": package, **entry}


def predictions_doi(record: Path, repo: Path) -> str | None:
    """The DOI of the predictions package whose preregistered test the record holds; None when it holds none."""
    deposit = _deposit(record, repo)
    return None if deposit is None else deposit["doi"]


def _public(record: Path, repo: Path, checks: dict) -> dict:
    """The claim results/claims.toml gives the signal (decision 0042), and each later listing its record excepts, with
    decision 0042's rule stated once."""
    name, tic = checks["signal"]["name"], int(checks["tic"])
    claim = load_claims(repo / CLAIMS).get(name)
    found = _claims(record) or {"claim": None, "excepted": []}
    rested = found["claim"]
    # The exception rests on the claim the claims run read; the paper states one claim, so the two must agree.
    if rested is not None and (
        claim is None or rested != {"date": claim.date.isoformat(), "record": claim.record}
    ):
        raise SystemExit(
            f"the record's claims.json rests on the claim {rested['date']} ({rested['record']}), not the one "
            f"{CLAIMS} gives {name}"
        )
    deposit = _deposit(record, repo)
    # A URL goes in Data Availability, out of the running text (AAS).
    at = ""
    if claim is None:
        where = None
    elif deposit is not None and claim.record == f"https://doi.org/{deposit['doi']}":
        where = f"in our predictions deposit ({_doi(deposit['doi'])})"
    elif claim.record.startswith("https://doi.org/"):
        where = f"in the record {_doi(claim.record.removeprefix('https://doi.org/'))}"
    elif claim.record.startswith("https://"):
        where = "in a public record, which Data Availability gives"
        at = f" The record that first made the signal public is at {claim.record}."
    else:
        where = f"in {claim.record}"
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    ratios = {m["name"]: m.get("ratio") for m in own["evidence"].get("matches") or []}
    excepted = found["excepted"]
    listings = []
    for r in excepted:
        dispositions = r["dispositions"]
        disposition = (
            f"disposition{'s' if len(dispositions) > 1 else ''} {_named(dispositions)}"
            if dispositions
            else "no disposition"
        )
        if r["name"] in ratios:
            listings.append(
                f" ExoFOP lists a signal at {_harmonic(ratios[r['name']])} on the star as {r['name']} (period "
                f"{r['period']:.6g} d, {disposition})."
            )
        else:
            also = " also" if listings else ""
            listings.append(
                f" ExoFOP{also} lists {r['name']} on the star (period {r['period']:.6g} d, {disposition})."
            )
        listings.append(
            f" ExoFOP first listed it on {_date(r['first_listed'])}, after we made the signal public."
        )
    if listings:
        them = f"the {excepted[0]['source']}" if len(excepted) == 1 else "them"
        listings.append(
            f" The vetting record does not say who submitted {them}. A listing made after our claim cannot show that "
            "the signal was known before the claim. Under DR 0042, a TOI or CTOI on the star is therefore not counted "
            "as known when ExoFOP first listed it after the claim and all its dispositions are PC or empty. Only "
            "public dates are compared, and nothing is implied about when or how anyone else found the signal."
        )
    return {
        "claim_date": None if claim is None else _date(claim.date),
        "claim_where": where,
        "claim_at": at,
        "exofop_page": EXOFOP_STAR.format(tic),
        "listings": "".join(listings),
    }


def _harmonic(ratio: float | None) -> str:
    """Where a listing the novelty check matched lies against the signal's period, by the harmonic it matched at."""
    return next(
        (said for k, said in HARMONICS.items() if ratio is not None and abs(ratio - k) < 1e-6),
        "a harmonic of this period",
    )


def _sector_start(repo: Path, sector: int) -> dt.date:
    rows = pd.read_csv(repo / SECTORS)
    found = rows.loc[rows["sector"] == sector, "start_utc"]
    if len(found) != 1:
        raise SystemExit(f"{SECTORS} gives no start for Sector {sector}")
    return dt.date.fromisoformat(str(found.iloc[0])[:10])


def _prereg(record: Path, repo: Path, call: dict) -> dict:
    """The preregistered test of a later season (decision 0040): when it was deposited, its result and what the result
    shows, and the Summary's sentence on it. A judged result without its depth or error leaves the paper's placeholder
    unfilled, so it raises. Refuses, before any run directory, a deposit Zenodo published on or after the day TESS
    began observing the first sector it predicts, since the paper says the prediction came first."""
    path = record / "prereg.json"
    if not path.is_file():
        return {
            "prereg": "This record holds no preregistered test of a later season (DR 0040)."
            + _upcoming(record),
            "summary_prereg": "",
            "conclusion_prereg": "",
        }
    p = json.loads(path.read_text())
    deposit = _deposit(record, repo)
    sectors = p["predicted_sectors"]
    first, published = min(sectors), deposit["published"]
    start = _sector_start(repo, first)
    if not published < start:
        raise SystemExit(
            f"refused: Zenodo published predictions package {p['package']} on {published}, not before TESS began "
            f"observing Sector {first} on {start}; the paper would say the prediction came before the data"
        )
    those = "that sector" if len(sectors) == 1 else "those sectors"
    deposited = (
        f"Before TESS observed {prereg._sectors_words(sectors)}, we deposited a prediction of the signal's transits in "
        f"{those} on Zenodo"
    )
    summary = f" {deposited}." + SUMMARY_RESULT[p["result"]]
    as_of = dt.date.fromisoformat(p["as_of"])
    if p["result"] == "pending":
        said = f"As of {_date(as_of)}, the test is pending ({_quote(p['reason'])})."
    elif p["result"] == "untested":
        said = f"As of {_date(as_of)}, the new data could not test the prediction ({_quote(p['reason'])})."
    else:
        depth, err = _ppm(p["depth"]), _ppm(p["err"])
        if depth is None or err is None:
            return {"summary_prereg": summary, "conclusion_prereg": CONCLUSION_RESULT[p["result"]]}
        verb = "replicate the signal" if p["result"] == "replicated" else "miss the prediction"
        said = (
            f"As of {_date(as_of)}, the new sectors {verb}. The {p['n']} cadences in the cores of the predicted "
            f"transits give a depth of {depth} ± {err} ppm, a significance of {p['sigma']:.2f}σ against the "
            f"{p['expected_snr']:.2f}σ the test expected."
        )
        if "tension" in p:
            said += (
                " Each light-curve family's new depth was compared with that family's depth in the earlier seasons, "
                f"as recorded in the deposit's `references.json`. The largest tension is {p['tension']:.2f}σ."
            )
        else:
            said += f" No tension was measured ({_quote(p['tension_skipped'])})."
        if p["result"] == "replicated":
            said += (
                " The replication shows that the transit is real and recurs at the predicted times. Which star it "
                "comes from remains open."
            )
    order = (
        "before" if call["date"] < as_of else "after" if call["date"] > as_of else "on the day of"
    )
    return {
        "prereg": f"{deposited} ({_doi(deposit['doi'])}). The deposit also fixed how the prediction would be judged: "
        "by the held-out check's criteria, applied to the predicted transits (DR 0040). Zenodo published the deposit "
        f"on {_date(published)}, and TESS began observing Sector {first} on {_date(start)}.{_upcoming(record)} "
        f"{said} Our call ({_date(call['date'])}) came {order} this result.",
        "summary_prereg": summary,
        "conclusion_prereg": CONCLUSION_RESULT[p["result"]],
    }


def _files(record: Path) -> str:
    """The dataset's guide: what each kind of file in the records holds, for the kinds the records have."""
    names = {_in_record(path) for path in _record_paths(record)}

    def held(pattern: str) -> bool:
        if pattern.endswith("/"):
            return any(n.startswith(pattern) for n in names)
        if "*" in pattern:
            head, tail = pattern.split("*")
            return any(n.startswith(head) and n.endswith(tail) and "/" not in n for n in names)
        return pattern in names

    return "**Table 4.** Files in each record\n\n" + _table(
        ["File", "What it holds"],
        [[f"`{pattern}`", what] for pattern, what in GUIDE if held(pattern)],
    )


def _records(signal: str, version: int | None) -> str:
    """Where the dataset holds each record: the first at the top of the signal's directory, each version below it."""
    if version is None:
        return f"The record is in `dataset/vetting/{signal}/`."
    if version == 2:
        return f"The first record is in `dataset/vetting/{signal}/` and version r2 in its `r2/` subdirectory."
    later = range(2, version + 1)
    return (
        f"The first record is in `dataset/vetting/{signal}/`, and versions {_words([f'r{n}' for n in later])} are in "
        f"its {_words([f'`r{n}/`' for n in later])} subdirectories."
    )


def _cites(keys) -> str:
    return "; ".join(REFERENCES[k][0] for k in keys)


def _reference_order(key: str) -> tuple:
    """AAS order, read from the citation the text gives each work: by first author, then a sole author before two
    before "et al.", then by year."""
    cite = REFERENCES[key][0]
    names, year = cite.rsplit(" ", 1)
    rank = 2 if names.endswith(" et al.") else 1 if " & " in names else 0
    first = names.removesuffix(" et al.").split(" & ")[0]
    return (first.casefold(), rank, year)


def _reference(entry: str) -> str:
    """One entry as HTML, with its DOI and its hyphenated words ("2-Minute", "Price-Whelan") each kept on one line."""
    work, has_doi, doi = escape(entry, quote=False).partition(", doi: ")
    work = re.sub(r"\w+(?:-\w+)+", lambda m: _id(m[0]), work)
    return f"<p>{work}, {_id(f'doi: {doi}')}</p>" if has_doi else f"<p>{work}</p>"


def _references(keys) -> str:
    """The reference list, one entry per paragraph with no labels, as HTML so the list keeps its hanging indent."""
    entries = [_reference(REFERENCES[k][1]) for k in sorted(set(keys), key=_reference_order)]
    return '<div class="references">\n' + "\n".join(entries) + "\n</div>"


def _data(record: Path, checks: dict, made: dict) -> dict:
    """The light curves' products and their citations, the dataset's records, the credits they ask for, and the
    reference list."""
    sectors: dict[str, list[int]] = {}
    for sector, source in checks["sources"].items():
        sectors.setdefault(prereg.PRODUCTS[source["provenance"]], []).append(int(sector))
    used = {product: sorted(sectors[product]) for product in prereg.CREDITED if product in sectors}
    signal = vetting._signal_dir(record).name
    gaia = any(licence(path)["licence"] == GAIA for path in _record_paths(record))
    version = calls.version(record)
    pdcsap = any(p in PDCSAP for p in used)
    products = _words(
        [
            f"{prereg.CREDITED[p][0]} from {prereg._sector_runs(s)} ({_cites(PRODUCT_REFERENCES[p])})"
            for p, s in used.items()
        ]
    )
    if pdcsap:
        products += f", with PDCSAP flux ({_cites(PDCSAP_REFERENCES)})"
    cited = [*CITED, *(k for p in used for k in PRODUCT_REFERENCES[p])]
    if pdcsap:
        cited += PDCSAP_REFERENCES
    return {
        "commit": made["git"]["commit"],
        "light_curve": f"lc/{int(checks['tic'])}.npz",
        "posterior_file": POSTERIOR,
        "products": products,
        "references": _references(cited),
        "facilities": "TESS, Gaia" if gaia else "TESS",
        "software": SOFTWARE,
        "diffimage": DIFFIMAGE,
        "records": _records(signal, version),
        "rendered_from": "that record" if version is None else f"version r{version}",
        "files": _files(record),
        "tess_credit": prereg.TESS_CREDIT,
        "qlp_credit": f" {prereg.QLP_CREDIT}" if "QLP" in used else "",
        "gaia_credit": GAIA_CREDIT if gaia else "",
    }


def _runs(record: Path, repo: Path, found: dict) -> str:
    """Table 3: the runs the paper reads, each by its run id and where its files are published."""
    signal = vetting._signal_dir(record).name
    benchmarks = [
        ("Search", found["search_run"]),
        ("Null search", found["null_run"]),
        ("Threshold", found["threshold_run"]),
        ("Injection recovery", found["inject_run"]),
    ]
    # A published run's directory is named by its run id, so the table gives the directory that holds it and keeps
    # each id on one line.
    rows = [[step, _id(run), "`results/benchmarks/`"] for step, run in benchmarks]
    rows.append(["Triage", _id(found["triage_run"]), "`results/triage/`"])
    for r in _versions(record):
        n = calls.version(r)
        made = json.loads((r / "provenance-checks.json").read_text())
        inside = "" if n is None else f"r{n}/"
        rows.append(
            [
                "Vetting, the first record" if n is None else f"Vetting, version r{n}",
                _id(made["run_id"]),
                f"`dataset/vetting/{signal}/{inside}`",
            ]
        )
    deposit = _deposit(record, repo)
    if deposit is not None:
        rows.append(
            [
                "Predictions package",
                _id(deposit["package"]),
                f"`results/predictions/`, {_doi(deposit['doi'])}",
            ]
        )
    return (
        "**Table 3.** Runs whose outputs this paper uses\n\n"
        + _table(["Step", "Run id", "Location of files"], rows)
        + "\n\n*Note.* The files of the search, null-search, threshold, injection-recovery, triage and predictions "
        "runs are in a directory named by the run id under the location given. A vetting run's provenance is the "
        "`provenance-checks.json` in its record's directory. Each provenance file names the command and the commit of "
        f"one run that wrote files in the record. The injection-recovery run's `{COMPLETENESS}` holds the recovered "
        "fraction as a function of expected signal-to-noise ratio."
    )


def _figures(record: Path) -> dict:
    """Each figure from the record's plots, with its number and the paper's caption, placed where the text cites it;
    none when the record lacks one, so their placeholders raise."""
    if any(not (record / "plots" / name).is_file() for name in FIGURES):
        return {}
    return {
        f"figure_{Path(name).stem}": (
            f'<figure>\n<img src="{name}" alt="Figure {i}">\n<figcaption><b>Figure {i}.</b> '
            + re.sub(r"`([^`]+)`", r"<code>\1</code>", CAPTIONS[name])
            + ".</figcaption>\n</figure>"
        )
        for i, name in enumerate(FIGURES, 1)
    }


def _author(author: dict, version: dt.date) -> dict:
    """The author block: the name, the affiliation, the ORCID and email when author.toml gives them, each on its own
    line, and the version's date."""
    lines = [f"{author['given_names']} {author['family_names']}", author["affiliation"]]
    if "orcid" in author:
        lines.append(f"ORCID {author['orcid']}")
    if "email" in author:
        lines.append(author["email"])
    block = "<br>".join(escape(line, quote=False) for line in lines)
    return {
        "author_block": f'<div class="front">\n<p class="author">{block}</p>\n'
        f'<p class="version">Version of {_date(version)}</p>\n</div>',
        "repository": author["repository"],
    }


def values(
    record: Path,
    author: dict,
    repo: Path,
    version: dt.date | None = None,
    posterior: dict | None = None,
) -> dict[str, str]:
    """Every placeholder of the template, read by key from the record, its runs' provenance, the published runs they
    name, results/claims.toml, results/predictions/dois.toml, benchmarks/tess_sectors.csv, `author` and the record's
    reproduced `posterior` (reproduced here when not given), formatted as the dossier formats them, with `version` as
    the paper's date (today by default). A value they don't hold is left out, so its placeholder raises."""
    version = version or dt.datetime.now(dt.UTC).date()
    posterior = posterior or reproduce(record)
    checks = json.loads((record / "checks.json").read_text())
    made = json.loads((record / "provenance-checks.json").read_text())
    call = calls.load(record / "call.toml")
    literature = json.loads((record / "literature.json").read_text())
    found = _found(repo, checks, made)
    out = (
        _star(checks, posterior)
        | _vetting(record, checks, call, literature)
        | _from_triceratops(record, checks["criteria_version"])
        | _review(record, calls.load_review(record / "review.json"), call, literature)
        | found
        | _public(record, repo, checks)
        | _data(record, checks, made)
        | _author(author, version)
        | _prereg(record, repo, call)
        | _figures(record)
        | {
            "history": _history(record),
            "runs": _runs(record, repo, found),
        }
    )
    return {key: value for key, value in out.items() if value is not None}


def render(
    record: Path,
    author: dict,
    repo: Path,
    version: dt.date | None = None,
    posterior: dict | None = None,
) -> str:
    """The paper in Markdown, dated `version` (the day it is rendered by default, the day its run starts). A specimen's
    text is a paper's: its PDF's header and footer mark it (`html`)."""
    return Template((repo / TEMPLATE).read_text()).substitute(
        values(record, author, repo, version, posterior)
    )


def html(markdown_text: str, specimen: bool) -> str:
    """The paper as the HTML page WeasyPrint lays out. With `specimen`, each page's header and footer say it is
    one."""
    # The optional preprint group's; the rest of tess-hunt runs without it.
    import markdown

    # toc gives each heading an id, which the stylesheet's section numbering reads.
    body = markdown.markdown(markdown_text, extensions=["tables", "toc"])
    # Hyphenation would split these names mid-word ("TRICER-ATOPS"); the Markdown keeps them plain.
    body = re.sub(r"\b(TRICERATOPS|LEO-Vetter)\b", r'<span class="id">\1</span>', body)
    style = STYLE + (SPECIMEN_STYLE if specimen else "")
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>{style}</style></head>'
        f"<body>{body}</body></html>"
    )


def document(markdown_text: str, assets: Path, specimen: bool):
    """The paper laid out by WeasyPrint, its figures read from `assets`."""
    import weasyprint

    page = html(markdown_text, specimen)
    return weasyprint.HTML(string=page, base_url=assets.resolve().as_uri() + "/").render()


def to_pdf(markdown_text: str, assets: Path, out: Path, specimen: bool) -> None:
    document(markdown_text, assets, specimen).write_pdf(out)


def _pdf_group() -> None:
    try:
        import markdown  # noqa: F401
        import weasyprint  # noqa: F401
    # WeasyPrint raises OSError when its system library, Pango, is missing.
    except (ImportError, OSError) as exc:
        raise SystemExit(
            f"the PDF needs the preprint dependency group: run `uv sync --group preprint` ({exc})"
        ) from None


def cmd_run(args) -> int:
    # Every refusal comes before the run starts, so it leaves no unfinished run directory.
    _pdf_group()
    repo = repo_root()
    record = passed_record(repo / "results" / "vetting" / args.name)
    # start_run's clean-tree check covers the code, not results/, so a production paper could otherwise be rendered from
    # a template, an author line or a claim nobody committed.
    if args.production and prereg._uncommitted(repo / "results"):
        raise SystemExit(
            "results/ has changes that are not committed; a production run needs them committed"
        )
    author = load_author(repo / AUTHOR)
    posterior = reproduce(record)
    text = render(record, author, repo, posterior=posterior)
    files = dataset(record)
    run = start_run("preprint", [], args.production, sys.argv)
    run.record("signal", args.name)
    run.record("record", str(record.relative_to(repo)))
    run.record("author", author)
    doi = predictions_doi(record, repo)
    run.record("predictions_doi", doi)
    read = [("template", TEMPLATE), ("author", AUTHOR), ("claims", CLAIMS)]
    for name, path in read + ([("dois", DOIS)] if doi else []):
        run.record_input(name, repo / path)
    (run.path / "preprint.md").write_text(text)
    for name in FIGURES:
        shutil.copyfile(record / "plots" / name, run.path / name)
    for name, path in files.items():
        target = run.path / "dataset" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    np.savez_compressed(run.path / "dataset" / POSTERIOR, **posterior)
    to_pdf(text, run.path, run.path / "preprint.pdf", specimen=False)
    manifest = [
        {
            "path": f"dataset/{name}",
            "sha256": sha256_file(run.path / "dataset" / name),
            **licence(name),
        }
        for name in [*files, POSTERIOR]
    ]
    run.write_json("manifest.json", {"signal": args.name, "files": manifest})
    run.finish(
        signal=args.name,
        record=str(record.relative_to(repo)),
        files=len(manifest),
        manifest_sha256=sha256_file(run.path / "manifest.json"),
    )
    print(
        f"preprint: {args.name} from {record.relative_to(repo)}, {len(manifest)} dataset files -> {run.path}"
    )
    return 0


def _package(source: Path) -> list[Path]:
    made = json.loads((source / "provenance.json").read_text())
    if made.get("stage") != "preprint":
        raise SystemExit(f"run {source.name} is not a preprint run")
    if not made.get("production"):
        raise SystemExit(
            f"run {source.name} is not a production run; only a production preprint is published"
        )
    return [source / name for name in PACKAGE]


def cmd_publish(args) -> int:
    publish_run(args.run, repo_root(), "preprints", _package)
    return 0


def _section(text: str, heading: str) -> str:
    return text.split(f"\n## {heading}\n")[1].split("\n## ")[0].strip()


def _plain(text: str) -> str:
    """The paper's inline HTML as plain text, for Zenodo's description box, which would show the tags: an
    asymmetric error as "(+0.12, −0.13)", a power as "^", the other tags dropped, and a record's text as written
    (`_literal`)."""
    text = re.sub(
        r'<span class="pm"><sup>([^<]*)</sup><sub>([^<]*)</sub></span>', r" (\1, \2)", text
    )
    text = re.sub(r"<sup>([^<]*)</sup>", r"^\1", text)
    text = re.sub(r"</?(sub|i|b|code)>", "", text)
    return unescape(re.sub(r"\\([\\`*_\[\]])", r"\1", text))


def deposit_form(run: Path) -> str:
    """The Zenodo deposit form's text for the paper and dataset a finished preprint run made, from the run's own
    files."""
    made = json.loads((run / "provenance.json").read_text())
    if made.get("stage") != "preprint":
        raise SystemExit(f"run {run.name} is not a preprint run")
    if made.get("ended_at") is None:
        raise SystemExit(f"run {run.name} has not finished")
    # The deposited copy is the committed one, and `publish` commits only a production run.
    if not made.get("production"):
        raise SystemExit(
            f"run {run.name} is not a production run; only a production preprint is deposited"
        )
    text = (run / "preprint.md").read_text()
    manifest = json.loads((run / "manifest.json").read_text())["files"]
    gaia = sorted(
        {_in_record(f["path"].removeprefix("dataset/")) for f in manifest if f["licence"] == GAIA}
    )
    author = made["author"]
    creators = f"- Name: {author['family_names']}, {author['given_names']}\n  Affiliation: {author['affiliation']}"
    if "orcid" in author:
        creators += f"\n  ORCID: {author['orcid']}"
    related = [
        f'- {author["repository"]} (URL), "Is supplemented by": tess-hunt\'s code and records'
    ]
    if made["predictions_doi"] is not None:
        related.insert(
            0,
            f'- {made["predictions_doi"]} (DOI), "References": the preregistered predictions whose test it reports',
        )
    # Each section's first paragraph: the Abstract without its keywords, which Zenodo takes in a field of its own, and
    # the Use of LLMs without the Facilities and Software lines below it.
    description = [
        _plain(_section(text, "Abstract").split("\n\n")[0]),
        "The deposit holds the paper (`preprint.pdf`, made from `preprint.md`), its figures and its dataset. The "
        "dataset holds the signal's published vetting records, the light curve that the vetting run of the paper's "
        "record read, and the samples of the density-prior fit behind Table 1's depth, duration and radius "
        f"(`{POSTERIOR}`). `manifest.json` lists each of its files with its sha256 and licence. The files are CC BY "
        "4.0, with two exceptions. The dataset's files that hold Gaia DR3 data "
        f"({_words([f'`{name}`' for name in gaia])}, in each record's directory) stay under ESA's CC BY-NC 3.0 IGO "
        "terms, as does any Gaia value in the paper's quoted text or notes. ExoFOP's rows in the dataset stay under "
        "ExoFOP's terms, as do the ExoFOP listings the paper names.",
        _section(text, "Use of LLMs").split("\n\n")[0],
    ]
    return ZENODO.substitute(
        run_id=made["run_id"],
        title=text.split("\n", 1)[0].removeprefix("# "),
        creators=creators,
        # Zenodo's description editor keeps line breaks, so each paragraph is pasted as one line.
        description="\n\n".join(" ".join(p.split()) for p in description),
        related="\n".join(related),
        figures="`, `".join(FIGURES),
    )


def cmd_zenodo(args) -> int:
    run = runs_dir() / args.run
    if not (run / "provenance.json").is_file():
        raise SystemExit(f"no run {args.run} under the data directory")
    print(deposit_form(run), end="")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "preprint", help="the Zenodo preprint and dataset for a passed signal (decision 0043)"
    )
    modes = p.add_subparsers(dest="mode", required=True)
    r = modes.add_parser(
        "run",
        help="render the paper, its PDF and its dataset from a signal's latest record, a pass that stands",
    )
    r.add_argument("--name", required=True, help="the signal's name under results/vetting/")
    r.add_argument("--production", action="store_true")
    r.set_defaults(func=cmd_run)
    pub = modes.add_parser("publish", help="copy a production preprint run into results/preprints/")
    pub.add_argument("--run", required=True, help="the run id")
    pub.set_defaults(func=cmd_publish)
    z = modes.add_parser(
        "zenodo", help="print the Zenodo deposit form's text for a finished preprint run"
    )
    z.add_argument("--run", required=True, help="the run id")
    z.set_defaults(func=cmd_zenodo)
