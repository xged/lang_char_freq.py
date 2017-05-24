import string
from copy import deepcopy

from lang_char_freqs import *

store = Path('.lang_char_freqs--CommitCharFreqs--test.pkl')

ccf = CommitCharFreqs(store=store)
ccf.add_repourls_lastupdated(npages=2, perpage=2, commit_limit=8, char_limit=2**12)
ccf.dump()
ccf = ccf.load()

def test_total():
    ccf2 = deepcopy(ccf)
    ccf2.unicase()
    assert ccf2.total(string.ascii_lowercase) == 0
    if ccf2.total("E") == 0:
        warn("You may want to rerun this test", RuntimeWarning)
    else:
        assert ccf2.total("ETA") > ccf2.total("TA") >= 0
    assert ccf2.total() == ccf.uni_charfreqs.total() == sum(ccf2.uni_counter.values()) > 0

def test_charfreqs():
    charfreqs = next(iter(ccf.d.values()))
    if charfreqs.total() == 0:
        warn("You may want to rerun this test", RuntimeWarning)
    assert charfreqs.total() == sum(charfreqs.uni_counter.values())

def test_add():
    ccf2 = deepcopy(ccf)
    ccf2.add(ccf, matched_add=True)
    assert ccf2.total() == 2 * ccf.total() and len(ccf2.d) == len(ccf.d)
    ccf2.add(ccf, matched_skip=True)
    assert ccf2.total() == 2 * ccf.total() and len(ccf2.d) == len(ccf.d)
    ccf2.add(ccf)
    assert ccf2.total() == ccf.total() and len(ccf2.d) == len(ccf.d)

def test_file():
    with TemporaryDirectory() as tempdir:
        ccf2 = deepcopy(ccf); ccf2.store = Path(tempdir) / store
        ccf2.save()
        assert ccf2.load().total() == ccf.total()
        ccf2 = deepcopy(ccf); ccf2.store = Path(tempdir) / store
        ccf2.save(matched_add=True)
        assert ccf2.load().total() == 2 * ccf.load().total() == 2 * ccf.total()
        ccf2.dump()
        assert ccf2.load().d == {}
