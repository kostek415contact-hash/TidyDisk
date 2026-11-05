Name:           tidydisk
Version:        2.23.11
Release:        1%{?dist}
Summary:        Free up disk space safely, with optional local AI review
License:        GPL-3.0-or-later
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
Requires:       python3-pyqt6
Requires:       polkit
Requires:       hicolor-icon-theme
Obsoletes:      fedora-cleaner < %{version}
Provides:       fedora-cleaner = %{version}

%description
TidyDisk finds caches, old kernels, unused packages, leftover installers
and duplicate files, explains every item and removes only what you confirm.
An optional local AI model can review the findings.

%prep
%autosetup -n %{name}-%{version}

%build
# nothing to build

%install
install -d %{buildroot}%{_datadir}/%{name}
cp -a tidydisk data %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name __pycache__ -type d -prune -exec rm -rf {} +
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/%{name} <<'SH'
#!/usr/bin/bash
export PYTHONPATH=%{_datadir}/%{name}${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m tidydisk "$@"
SH
chmod 755 %{buildroot}%{_bindir}/%{name}
install -Dm644 data/tidydisk.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{name}.svg
for d in data/icons/*x*/; do
  size=$(basename "$d")
  install -Dm644 "$d/tidydisk.png" %{buildroot}%{_datadir}/icons/hicolor/$size/apps/%{name}.png
done
install -Dm644 data/tidydisk.desktop %{buildroot}%{_datadir}/applications/%{name}.desktop
install -Dm644 data/tidydisk.metainfo.xml %{buildroot}%{_metainfodir}/%{name}.metainfo.xml
install -Dm644 data/org.tidydisk.admin-scan.policy %{buildroot}%{_datadir}/polkit-1/actions/org.tidydisk.admin-scan.policy
# skaner administratora: kopia nalezaca do roota, generowana z kodu pakietu
install -d %{buildroot}%{_libexecdir}/%{name}
TIDYDISK_NO_MIGRATE=1 PYTHONPATH=. python3 -I -c '
import sys; sys.path.insert(0, ".")
from tidydisk import scanner, __version__
sys.stdout.write(scanner.build_admin_source("/", "", (), argv=True, version=__version__))' > %{buildroot}%{_libexecdir}/%{name}/admin_scan.py
chmod 755 %{buildroot}%{_libexecdir}/%{name}/admin_scan.py

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/%{name}.desktop

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/%{name}.desktop
%{_metainfodir}/%{name}.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/%{name}.*
%{_datadir}/polkit-1/actions/org.tidydisk.admin-scan.policy
%{_libexecdir}/%{name}/

%changelog
* Thu Nov 05 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.11-1
- Poprawki po audycie: anonimizacja sciezek, uczenie, CLI, historia, okno
* Thu Nov 05 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.10-1
- Rownolegle zapisy plikow, anonimizacja, historia czesciowego czyszczenia, poprawki CLI i okna
* Thu Nov 05 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.9-1
- Ochrona zagniezdzonych .ssh/.gnupg/.git, poprawki czyszczenia, raportow i AI
* Thu Nov 05 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.8-1
- Naprawa bledu okna po czyszczeniu, historia z nazwami w zlym kodowaniu
* Thu Nov 05 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.7-1
- Naprawa regresji z 2.23.6 oraz poprawki GUI
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.6-1
- Ochrona stref Nie ruszaj, kontrola przed usunieciem, kosz na dyskach
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.5-1
- Poprawki po pelnym audycie
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.4-1
- Drobne poprawki po audycie koncowym
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.3-1
- holds_keep: bez falszywych odmow dla glebokich folderow
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.2-1
- Poprawki po audycie: kosz i ochrona folderow, CLI, GUI
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.1-1
- Windows: poprawki bezpieczenstwa i spojnosci sciezek, tidydisk-gui.exe w harmonogramie
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.23.0-1
- Windows: AI scheduler task, auto-clean option, empty-file suggestions, UNC paths

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.22.1-1
- Ignore empty files in version detection

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.22.0-1
- Windows: file analysis, AI and scheduler support

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.21.2-1
- Windows: assign drive to scan entries

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.21.1-1
- Windows: protect NTUSER.DAT and profile system files

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.21.0-1
- Windows: cleaning enabled (winfs backend)

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.20.3-1
- Windows: correct file ratings, hide unsupported AI buttons

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.20.2-1
- Windows GUI executable built in CI

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.20.1-1
- Fix disk usage total for multi-partition btrfs

* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.20.0-1
- Audit fixes: race-free deletion, report masking, Windows console build
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.18.0-1
- Renamed from fedora-cleaner (Obsoletes/Provides keep upgrades working)
* Wed Nov 04 2026 TidyDisk contributors <noreply@example.invalid> - 2.16.0-1
- See CHANGELOG.md
