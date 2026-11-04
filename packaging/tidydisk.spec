Name:           tidydisk
Version:        2.19.2
Release:        1%{?dist}
Summary:        Free up disk space safely, with optional local AI review
License:        GPL-3.0-or-later
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
Requires:       python3-pyqt6
Requires:       polkit
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
PYTHONPATH=. python3 -I -c '
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
* Wed Nov 04 2026 TidyDisk contributors - 2.19.2-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.16.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.15.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.14.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.13.1-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.13.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.12.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.11.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.10.1-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.10.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.9.3-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.9.2-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.9.1-1
- Package for Fedora (RPM); see CHANGELOG.md

* Wed Nov 04 2026 TidyDisk contributors - 2.9.0-1
- Package for Fedora (RPM); see CHANGELOG.md

* Tue Nov 03 2026 TidyDisk contributors - 2.8.1-1
- Package for Fedora (RPM); see CHANGELOG.md
