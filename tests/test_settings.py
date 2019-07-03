import pytest

from galacteek.appsettings import *


@pytest.fixture
def mgr(tmpdir):
    filep = tmpdir.join('settings.txt')
    return SettingsManager(str(filep))


class TestSettings:
    @pytest.mark.parametrize('sec', ['SEC1', 'SEC190'])
    @pytest.mark.parametrize('name', ['NAME1'])
    @pytest.mark.parametrize('value', ['POID1233902'])
    def test_simple(self, mgr, sec, name, value):
        mgr.setDefaultSetting(sec, name, value)

        assert mgr.getSetting(sec, name) == value
        with pytest.raises(Exception):
            mgr.getSetting(sec, name, int)

    @pytest.mark.parametrize('sec', ['SEC1'])
    @pytest.mark.parametrize('name', ['NAME1'])
    def test_booleans(self, mgr, sec, name):
        mgr.setTrue(sec, name)

        assert mgr.isTrue(sec, name)
        assert mgr.isFalse(sec, name) is False
