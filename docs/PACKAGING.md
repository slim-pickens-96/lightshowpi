# Packaging and publishing

This version is distributed as a **source tarball plus `install.sh`**. That's
how LightShow Pi has always been installed, and it needs no build step: the
installer gets dependencies from apt and creates a local `.venv`.

## Build a release

```bash
cd lightshowpi
git status                 # commit everything first, only committed files are packaged
echo 3.2.1 > VERSION       # bump the version if this is a new release
git commit -am "Release 3.2.1"
git tag -a v3.2.1 -m "LightShow Pi 3.2.1"
tools/build_release.sh     # or: tools/build_release.sh v3.2.1
```

This produces:

```
dist/lightshowpi-<VERSION>.tar.gz          # top folder: lightshowpi-<VERSION>/
dist/lightshowpi-<VERSION>.tar.gz.sha256
```

`build_release.sh` uses `git archive`, so local files never end up in a
release: `config/overrides.cfg`, `.venv`, logs, `.sync` caches and test
output are all left out. If you have uncommitted changes, it warns you and
leaves them out.

## Check a release before publishing

```bash
cd /tmp && tar xzf ~/lightshowpi/dist/lightshowpi-<VERSION>.tar.gz
cd lightshowpi-<VERSION>
sha256sum -c ~/lightshowpi/dist/lightshowpi-<VERSION>.tar.gz.sha256   # run in dist/
./install.sh --dry-run                     # shows what it would do, changes nothing
python3 -m venv /tmp/t && /tmp/t/bin/pip install numpy mutagen pytest
LIGHTSHOWPI_PYTHON=/tmp/t/bin/python /tmp/t/bin/python -m pytest -q tests
```

Ideally, also do one real `sudo ./install.sh` on a spare SD card with
Raspberry Pi OS (bookworm or trixie), then run `lightshowpi doctor` and
`lightshowpi test`.

## Install from a release (users)

```bash
wget https://<your-release-host>/lightshowpi-<VERSION>.tar.gz
wget https://<your-release-host>/lightshowpi-<VERSION>.tar.gz.sha256
sha256sum -c lightshowpi-<VERSION>.tar.gz.sha256
tar xzf lightshowpi-<VERSION>.tar.gz
mv lightshowpi-<VERSION> ~/lightshowpi && cd ~/lightshowpi
sudo ./install.sh
```

## Publishing

**Nothing has been pushed anywhere.** The working copy is a local git
repository on the branch `modernize`. It has two remotes: `upstream` (the
original Bitbucket repository, <https://bitbucket.org/togiles/lightshowpi>)
and `upstream-local` (a local clone). **Don't push to `upstream`.** It
belongs to the original authors, and changes there should go through them.

To publish on your own GitHub account:

```bash
# 1. Create an empty repository on GitHub (no README), e.g. you/lightshowpi
cd lightshowpi
git remote add origin git@github.com:<you>/lightshowpi.git
git push -u origin modernize          # the full history, upstream commits included
git push origin v3.2.1                # the tag
# 2. On GitHub: Releases -> Draft a new release -> choose tag v3.2.1,
#    attach dist/lightshowpi-3.2.1.tar.gz and the .sha256 file,
#    and paste the summary from docs/CHANGES.md.
```

Or, with the GitHub CLI:

```bash
gh repo create <you>/lightshowpi --public --source=. --remote=origin --push
gh release create v3.2.1 dist/lightshowpi-3.2.1.tar.gz dist/lightshowpi-3.2.1.tar.gz.sha256 \
    --title "LightShow Pi 3.2.1" --notes-file docs/CHANGES.md
```

Before publishing:

- Keep `LICENSE` (BSD) and the contributors list in `README.md`.
- Say clearly in the README that this is a community-modernized fork, and link to the original project.
- Consider offering the changes to the original maintainers (Bitbucket pull request or the [r/LightShowPi subreddit](https://www.reddit.com/r/LightShowPi/)). There has been an [open call for help updating the project](https://www.reddit.com/r/LightShowPi/comments/1g35kjf/anyone_want_to_assist_with_updating_the_project/).
- Update the `git clone` URL in `docs/INSTALL.md` to point at your repository.

## Future packaging options (not done)

- **Debian package (`.deb`)**: install to `/opt/lightshowpi` with
  `Depends: python3-numpy, python3-mutagen, python3-alsaaudio, ffmpeg, python3-lgpio | ...`
  and the systemd unit as a conffile. This would make
  `sudo apt install ./lightshowpi_*.deb` possible. It needs maintainer
  scripts for the `gpio` group and user config, plus testing on real Raspberry
  Pi OS.
- **PyPI**: not a good fit. The code expects a writable install folder (config,
  logs, music, `.sync` caches) and depends on apt-only packages such as lgpio
  and ffmpeg.
- **Containers**: not recommended. See the compatibility decisions in
  [CHANGES.md](CHANGES.md).
