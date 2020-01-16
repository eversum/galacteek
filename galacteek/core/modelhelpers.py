from async_generator import async_generator, yield_, yield_from_
import asyncio
import re

from PyQt5.QtGui import QStandardItem
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal


""" Helper functions to operate on QT item models """


def modelWalk(model, parent=QModelIndex(), search=None,
              searchre=None, columns=None, delete=False, dump=False,
              reflags=re.IGNORECASE, maxdepth=0, depth=0):
    """Walk over every model index in the given model looking for data matching
    the search parameter (or searchre if you want to use a regexp)

    Yields matching model indexes

    :param QAbstractItemModel model: the QT model
    :param QModelIndex parent: the parent item index in the model
    :param list columns: integer list of columns to search
    :param str search: string to search
    :param str searchre: regexp to search
    :param int reflags: regexp flags passed to re.search
    :param bool delete: delete matching indexes
    :param int maxdepth: maximum tree depth
    :return: list of matching indexes
    """

    for row in range(0, model.rowCount(parent)):
        index0 = model.index(row, 0, parent)
        if columns:
            cols = columns
        else:
            cols = [c for c in range(0, model.columnCount(parent))]
        for col in cols:
            index = model.index(row, col, parent)
            if not index:
                continue
            data = model.data(index, Qt.EditRole)
            if search:
                if search == str(data):
                    if delete:
                        model.removeRow(row, parent)
                        model.submit()
                    yield index
            if searchre:
                if re.search(searchre, str(data), reflags):
                    yield index
        if model.hasChildren(index0):
            if maxdepth == 0 or (maxdepth > depth):
                yield from modelWalk(
                    model, parent=index0,
                    search=search, columns=columns, delete=delete,
                    dump=dump, searchre=searchre, reflags=reflags,
                    maxdepth=maxdepth, depth=depth)
                depth += 1


def modelSearch(model, parent=QModelIndex(), columns=None, delete=False,
                search=None, searchre=None, reflags=re.IGNORECASE):
    """Searches data in a QT model, see modelWalk for more info on
    parameters"""
    return list(modelWalk(model, parent=parent, columns=columns,
                          search=search, delete=delete, searchre=searchre,
                          reflags=reflags))


def modelDelete(model, search):
    """Delete items matching search from a QT model """
    return list(modelSearch(model, search=search, delete=True))


""" Asynchronous equivalents for when calling from coroutines """


@async_generator
async def modelWalkAsync(model, parent=QModelIndex(), search=None,
                         columns=None, delete=False, dump=False,
                         maxdepth=0, depth=0):
    for row in range(0, model.rowCount(parent)):
        await asyncio.sleep(0)

        index0 = model.index(row, 0, parent)
        if columns:
            cols = columns
        else:
            cols = [c for c in range(0, model.columnCount(parent))]
        for col in cols:
            index = model.index(row, col, parent)
            if not index:
                continue
            data = model.data(index, Qt.EditRole)
            if search:
                if search == data:
                    if delete:
                        model.removeRow(row, parent)
                        model.submit()
                    await yield_(index)
        await asyncio.sleep(0)
        if model.hasChildren(index0):
            if maxdepth == 0 or (maxdepth > depth):
                await yield_from_(modelWalkAsync(
                    model, parent=index0,
                    search=search, columns=columns, delete=delete,
                    dump=dump, maxdepth=maxdepth, depth=depth))
                depth += 1


async def modelSearchAsync(model, parent=QModelIndex(), search=None,
                           columns=None, delete=False, maxdepth=0, depth=0):
    items = []
    async for v in modelWalkAsync(model, parent=parent, columns=columns,
                                  search=search, delete=delete,
                                  maxdepth=maxdepth, depth=depth):
        items.append(v)
    return items


async def modelDeleteAsync(model, search):
    return await modelSearchAsync(model, search=search, delete=True)


class UneditableItem(QStandardItem, QObject):
    refreshes = pyqtSignal()

    def __init__(self, text, icon=None):
        if icon:
            super(UneditableItem, self).__init__(icon, text)
        else:
            super(UneditableItem, self).__init__(text)
        self.setEditable(False)
