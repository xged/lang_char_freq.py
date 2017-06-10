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

MAXINT = 10**9

class CharFreqs():
    def __init__(self, d: Dict[FExten, Counter]=None) -> None:
        if d is None: d = {}
        self.d = d

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
        if d is None: d = {}
        if store is None: store = Path('.CommitCharFreqs-store.pkl')
        self.d = d
        self.store = store

    def append(self, repourl: RepoUrl, charfreqs: CharFreqs, matched_skip: bool=None, matched_add: bool=None) -> None:
        if repourl in self.d:
            if matched_skip:
                return
            elif matched_add:
                self.d[repourl].add(charfreqs)
                return
        self.d[repourl] = charfreqs

    def add(self, ccf: 'CommitCharFreqs', matched_skip: bool=None, matched_add: bool=None) -> None:
        for repourl in ccf.d:
            self.append(repourl, ccf.d[repourl], matched_skip, matched_add)

    def add_dir(self, dir: Path, commit_limit: int=None, char_limit: int=None, matched_skip: bool=None, matched_add: bool=None) -> None:
        if commit_limit is None: commit_limit = MAXINT
        if char_limit is None: char_limit = MAXINT
        repourl = cmd.git['-C', str(dir), 'remote', 'get-url', 'origin']()
        print(repourl, ':')
        charfreqs = CharFreqs()
        commits = cmd.git['-C', str(dir), 'log', '-n', commit_limit, '--pretty=format:%H']().split()
        for i, commit in enumerate(commits):
            for diff in parse_patch(cmd.git['-C', str(dir), 'diff', commit]()):
                if diff.changes:
                    addedlines = [l for loc, _, l in diff.changes if loc == None]
                    charfreqs.append(Path(diff.header.new_path).suffix, Counter('\n'.join(addedlines[-char_limit:])))
            print(i+1, "commits crunched.", end='\r')  #%
        print()
        self.append(repourl, charfreqs, matched_skip, matched_add)

    def add_repourl(self, repourl: RepoUrl, commit_limit: int=None, char_limit: int=None, matched_skip: bool=None, matched_add: bool=None, silent: bool=None) -> None:
        with TemporaryDirectory() as tempdir:
            git_clone(repourl, Path(tempdir), commit_limit, silent)
            self.add_dir(Path(tempdir), commit_limit, char_limit, matched_skip, matched_add)

    def add_repourls_lastupdated(self, npages: int=None, perpage: int=None, commit_limit: int=None, char_limit: int=None, matched_skip: bool=None, matched_add: bool=None, silent: bool=None) -> None:
        for repourl in fetch_repourls_lastupdated(npages, perpage):
            self.add_repourl(repourl, commit_limit, char_limit, matched_skip, matched_add, silent)

    def add_repourls_lastupdated_max(self, *args, **kwargs) -> None:
        self.add_repourls_lastupdated(10, 100, *args, **kwargs)

    def load(self, f: Path=None) -> 'CommitCharFreqs':
        if f is None: f = self.store
        with f.open('rb') as file:
            return pickle.load(file)

    def dump(self, f: Path=None) -> None:
        if f is None: f = self.store
        print("Writing to {!r}...".format(f))
        with f.open('wb') as file:
            pickle.dump(self, file)

    def save(self, f: Path=None, matched_skip: bool=None, matched_add: bool=None) -> None:
        if f is None: f = self.store
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

def git_clone(repourl: RepoUrl, dir: Path, commit_limit: int=None, silent: bool=None):
    if commit_limit is None: commit_limit = MAXINT
    if not silent:
        cmd.git['clone', repourl, dir, '--depth', commit_limit, '--shallow-submodules'] & FG
    else:
        cmd.git['clone', repourl, dir, '--depth', commit_limit, '--shallow-submodules']()

def fetch_repourls_lastupdated(npages: int=None, perpage: int=None) -> Set[RepoUrl]:
    if npages is None: npages = 1
    if perpage is None: perpage = 1
    assert npages >= 1
    assert perpage in range(1, 100+1)
    nresults = npages * perpage
    if nresults > 1000:
        warn('Github API limit: 1,000 search results', RuntimeWarning)
    print('Fetching {} recently updated Github repo urls...'.format(nresults))
    repourls = set()
    for pagenr in range(1, npages + 1):
        r = requests.get('https://api.github.com/search/repositories', {'q': 'stars:>0', 'sort': 'updated', 'per_page': perpage, 'page': pagenr})
        for item in r.json()['items']:
            try:
                repourls.add(item['clone_url'])
            except KeyError:
                warn('', RuntimeWarning)  #?
    return repourls
