import pickle
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Set
from warnings import warn

import requests
from plumbum import FG, cmd
from whatthepatch import parse_patch

RepoUrl = str  # Github.com
FExten = str  # file extension (".py")
Hash = str

MAXINT = 10**9

class CharFreqs():
    def __init__(self, d: Dict[FExten, Counter]=None) -> None:
        self.d = d or {}

    def append(self, fexten: FExten, counter: Counter) -> None:
        self.d[fexten] = self.d.get(fexten, Counter()) + counter

    def add(self, charfreqs: 'CharFreqs') -> None:
        for fexten in charfreqs.d:
            self.append(fexten, charfreqs.d[fexten])

    def unicase(self) -> None:
        for fexten in self.d:
            counter = Counter()
            for c in self.d[fexten]:
                counter.update({c.upper(): self.d[fexten][c]})
            self.d[fexten] = counter

    def total(self, chars: str=None) -> int:
        if chars is None:  # all chars
            return sum((sum(counter.values()) for counter in self.d.values()))
        return sum((counter[c] for c in chars for counter in self.d.values()))

    @property
    def uni_counter(self) -> Counter:
        return sum(self.d.values(), Counter())

class CommitCharFreqs():
    def __init__(self, d: Dict[RepoUrl, CharFreqs]=None, store: Path=None) -> None:
        self.d = d or {}
        self.store = store or Path('.CommitCharFreqs-store.pkl')

    def append(self, repourl: RepoUrl, charfreqs: CharFreqs, matched_skip=False, matched_add=False) -> None:
        if repourl in self.d:
            if matched_skip:
                return
            elif matched_add:
                self.d[repourl].add(charfreqs)
                return
        self.d[repourl] = charfreqs

    def add(self, ccf: 'CommitCharFreqs', matched_skip=False, matched_add=False) -> None:
        for repourl in ccf.d:
            self.append(repourl, ccf.d[repourl], matched_skip, matched_add)

    def add_commit(self, dir: Path, commit: Hash, repourl: RepoUrl=None, commit_limit=MAXINT, char_limit=MAXINT, matched_skip=False, matched_add=False):
        repourl = repourl or cmd.git['-C', str(dir), 'remote', 'get-url', 'origin']()
        charfreqs = CharFreqs()
        for diff in parse_patch(cmd.git['-C', str(dir), 'diff', commit]()):
            if diff.changes:
                addedlines = [l for loc, _, l in diff.changes if loc == None]
                charfreqs.append(Path(diff.header.new_path).suffix, Counter('\n'.join(addedlines[-char_limit:])))
        self.append(repourl, charfreqs, matched_skip, matched_add)

    def add_dir(self, dir: Path, repourl: RepoUrl=None, commit_limit=MAXINT, char_limit=MAXINT, matched_skip=False, matched_add=False) -> None:
        repourl = repourl or cmd.git['-C', str(dir), 'remote', 'get-url', 'origin']()
        print(repourl, ':')
        commits = cmd.git['-C', str(dir), 'log', '-n', commit_limit, '--pretty=format:%H']().split()
        for i, commit in enumerate(commits):
            self.add_commit(dir, commit, repourl, commit_limit, char_limit)
            print(i+1, "commits crunched.", end='\r')
        print()

    def add_repourl(self, repourl: RepoUrl, commit_limit=MAXINT, char_limit=MAXINT, matched_skip=False, matched_add=False) -> None:
        with TemporaryDirectory() as tempdir:
            cmd.git['clone', repourl, Path(tempdir), '--depth', commit_limit, '--shallow-submodules'] & FG
            self.add_dir(Path(tempdir), repourl, commit_limit, char_limit, matched_skip, matched_add)

    def add_repourls_lastupdated(self, npages=1, perpage=1, max=False, commit_limit=MAXINT, char_limit=MAXINT, matched_skip=False, matched_add=False) -> None:
        for repourl in fetch_repourls_lastupdated(npages, perpage):
            self.add_repourl(repourl, commit_limit, char_limit, matched_skip, matched_add)

    def load(self, f: Path=None) -> 'CommitCharFreqs':
        f = f or self.store
        with f.open('rb') as file:
            return pickle.load(file)

    def dump(self, f: Path=None) -> None:
        f = f or self.store
        print("Writing to {!r}...".format(f))
        with f.open('wb') as file:
            pickle.dump(self, file)

    def save(self, f: Path=None, matched_skip=False, matched_add=False) -> None:
        f = f or self.store
        if f.exists():
            self.add(self.load(f), matched_skip, matched_add)
        self.dump(f)
        print("Added {} items to {}".format(len(self.d), f))
        self.d = {}

    def unicase(self) -> None:
        for repourl in self.d:
            self.d[repourl].unicase()

    def total(self, chars: str=None) -> int:
        if chars is None:  # all chars
            return sum((self.d[fexten].total() for fexten in self.d))
        return sum((ccf.total(chars) for ccf in self.d.values()))

    @property
    def uni_counter(self) -> Counter:
        return sum((ccf.uni_counter for ccf in self.d.values()), Counter())

    @property
    def uni_charfreqs(self) -> CharFreqs:
        charfreqs = CharFreqs()
        for cf in self.d.values():
            charfreqs.add(cf)
        return charfreqs

def fetch_repourls_lastupdated(npages=1, perpage=1, max=False) -> Set[RepoUrl]:
    if max:
        npages = 10; perpage = 100
        nresults = 1000
    else:
        assert npages >= 1 and perpage in range(1, 100+1)
        nresults = npages * perpage
        if nresults > 1000:
            warn('Github API limit: 1,000 search results', RuntimeWarning)
    print('Fetching {} recently updated Github repo urls...'.format(nresults))
    repourls = set()
    for pagenr in range(1, npages + 1):
        r = requests.get('https://api.github.com/search/repositories', {'q': 'stars:>0', 'sort': 'updated', 'per_page': perpage, 'page': pagenr})
        for item in r.json().get('items', {}):
            repourls.add(item.get('clone_url', None))
    return repourls
