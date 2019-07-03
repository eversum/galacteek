import pytest

from PyQt5.QtGui import QStandardItemModel, QStandardItem

from galacteek.core.modelhelpers import *


@pytest.fixture
def model():
    return QStandardItemModel()


@pytest.fixture
def stditem():
    item = QStandardItem('test')
    return item


class TestModel:
    def test_search(self, model, stditem):
        model.invisibleRootItem().appendRow(stditem)

        idxes = modelSearch(model, search='test')
        assert idxes.pop() == stditem.index()

        idxes = modelSearch(model, searchre='.*est')
        assert idxes.pop() == stditem.index()

        idxes = modelSearch(model, searchre='TEST', reflags=0)
        assert len(idxes) == 0

    def test_delete(self, model, stditem):
        model.invisibleRootItem().appendRow(stditem)
        item2 = QStandardItem('test2')
        item3 = QStandardItem('test3')
        stditem.appendRow([item2, item3])

        modelDelete(model, 'test3')
        idxes = modelSearch(model, search='test3')
        assert len(idxes) == 0
