Summary:       Asynchronous Python HTTP Requests for Humans
Name:          python-requests-futures
Version:       0.9.9
Release:       1%{?dist}
License:       Python
Group:         Development/Libraries
URL:           https://github.com/ross/requests-futures
Source0:       https://github.com/ross/requests-futures/archive/v%{version}.tar.gz
BuildRequires: python2-devel
BuildRequires: python2-setuptools
BuildArch:     noarch

%description
mall add-on for the python requests http library. Makes use of python 3.2's concurrent.futures or the backport for prior versions of python.

The additional API and changes are minimal and strives to avoid surprises.

%package -n python2-requests-futures
Summary:        %{summary}
%{?python_provide:%python_provide python2-futures}
Provides:  python-requests-futures = %{version}-%{release}
Obsoletes: python-requests-futures < %{version}-%{release}

%description -n python2-requests-futures
Small add-on for the python requests http library. Makes use of python 3.2's concurrent.futures or the backport for prior versions of python.

The additional API and changes are minimal and strives to avoid surprises.

%prep
%setup -q -n requests-futures-%{version}

%build
%{py2_build}

%install
%{py2_install}

%files -n python2-requests-futures
%license LICENSE
# %doc CHANGES
%{python2_sitelib}/requests_futures
%{python2_sitelib}/requests_futures-*.egg-info*

%changelog
* Wed Apr 10 2019 Tim Shelton <tshelton@hawkdefense.com> - 0.9.9-1
- Initial package

