"""Atrapa PyQt6 do testowania logiki okna bez Qt (wszystko, co nieznane, to 'Dummy')."""
import sys
import types


class Val(int):
    """Wartosc enuma: wspiera | i .value."""
    def __new__(cls, n=0):
        return int.__new__(cls, n)

    @property
    def value(self):
        return int(self)

    def __or__(self, o):
        return Val(int(self) | int(o))

    def __getattr__(self, name):  # zagniezdzone enumy: Qt.ItemDataRole.UserRole
        if name.startswith("__"):
            raise AttributeError(name)
        fixed = {"UserRole": 256, "Unchecked": 0, "PartiallyChecked": 1, "Checked": 2}
        return Val(fixed[name] if name in fixed else (sum(map(ord, name)) % 997) * 4 + 8)


class NS:
    def __init__(self):
        self._n = 0
        self._d = {}

    def __call__(self, *a, **k):
        return Dummy()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name not in self._d:
            self._n += 1
            self._d[name] = Val(self._n * 4) if name != "UserRole" else Val(256)
            if name in ("Unchecked",):
                self._d[name] = Val(0)
            if name == "PartiallyChecked":
                self._d[name] = Val(1)
            if name == "Checked":
                self._d[name] = Val(2)
        return self._d[name]


class Dummy:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Dummy()

    def __call__(self, *a, **k):
        return Dummy()

    def pointSizeF(self):
        return 10.0

    def __or__(self, o):
        return self

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return True


class _Sig:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self, *a):
        for s in list(self.slots):
            s(*a)


class pyqtSignal:
    def __init__(self, *types_):
        pass

    def __set_name__(self, owner, name):
        self.name = "_sig_" + name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        if self.name not in obj.__dict__:
            obj.__dict__[self.name] = _Sig()
        return obj.__dict__[self.name]


class QThread(Dummy):
    def start(self):
        self.started_flag = True

    def isRunning(self):
        return False

    def wait(self, *a):
        return True


class FakeItem(Dummy):
    def __init__(self, a=None, b=None):
        self._data, self._text, self._check, self._hidden = {}, [], {}, False
        self._children, self._parent, self._exp = [], None, False
        if isinstance(a, FakeItem):
            self._parent = a
            a._children.append(self)
            self._text = list(b or [])
        elif isinstance(a, (list, tuple)):
            self._text = list(a)

    def text(self, c):
        return self._text[c] if c < len(self._text) else ""

    def setText(self, c, t):
        while len(self._text) <= c:
            self._text.append("")
        self._text[c] = t

    def setData(self, c, role, v):
        self._data[(c, int(role))] = v

    def data(self, c, role):
        return self._data.get((c, int(role)))

    def setCheckState(self, c, s):
        self._check[c] = int(s)

    def checkState(self, c):
        return Val(self._check.get(c, 0))

    def childCount(self):
        return len(self._children)

    def child(self, i):
        return self._children[i]

    def takeChild(self, i):
        return self._children.pop(i)

    def parent(self):
        return self._parent

    def setHidden(self, h):
        self._hidden = h

    def isHidden(self):
        return self._hidden

    def setExpanded(self, e):
        self._exp = e

    def isExpanded(self):
        return self._exp


class FakeTree(Dummy):
    def __init__(self, *a):
        self._root = FakeItem()
        self.itemChanged = _Sig()
        self.itemExpanded = _Sig()
        self.currentItemChanged = _Sig()
        self.itemDoubleClicked = _Sig()
        self.customContextMenuRequested = _Sig()

    def clear(self):
        self._root = FakeItem()

    def invisibleRootItem(self):
        return self._root

    def addTopLevelItem(self, it):
        it._parent = None
        self._root._children.append(it)

    def topLevelItemCount(self):
        return len(self._root._children)

    def topLevelItem(self, i):
        return self._root._children[i]


class FakeCombo(Dummy):
    def __init__(self, *a):
        self._items = []
        self._idx = 0
        self.currentIndexChanged = _Sig()

    def addItem(self, t, d=None):
        self._items.append((t, d))

    def clear(self):
        self._items, self._idx = [], 0

    def findData(self, d):
        return next((i for i, (_t, v) in enumerate(self._items) if v == d), -1)

    def currentIndex(self):
        return self._idx

    def currentData(self):
        return self._items[self._idx][1] if self._items else None

    def set(self, i):
        self._idx = i

    def count(self):
        return len(self._items)

    def itemData(self, i):
        return self._items[i][1]

    def setCurrentIndex(self, i):
        self._idx = i


class FakeEdit(Dummy):
    EchoMode = NS()

    def __init__(self, *a):
        self._t = ""
        self.textChanged = _Sig()

    def text(self):
        return self._t

    def setText(self, t):
        self._t = t

    def set(self, t):
        self._t = t
        self.textChanged.emit(t)


class FakeLabel(Dummy):
    def __init__(self, text="", *a):
        self._t = text

    def setText(self, t):
        self._t = t

    def text(self):
        return self._t


class FakeCheck(Dummy):
    def __init__(self, *a):
        self._c = False
        self.toggled = _Sig()

    def isChecked(self):
        return self._c

    def setChecked(self, v):
        self._c = bool(v)


class FakeSpin(Dummy):
    def __init__(self, *a):
        self._v = 0

    def value(self):
        return self._v

    def setValue(self, v):
        self._v = v

    def set(self, v):
        self._v = v


class FakeText(Dummy):
    def __init__(self, *a):
        self._t = ""

    def toPlainText(self):
        return self._t

    def setPlainText(self, t):
        self._t = t


class FakeAction(Dummy):
    def __init__(self, *a):
        self._c = False
        self.triggered = _Sig()
        self.toggled = _Sig()

    def setCheckable(self, v):
        pass

    def setChecked(self, v):
        self._c = v

    def isChecked(self):
        return self._c


class FakeStack(Dummy):
    def __init__(self, *a):
        self._i = 0
        self._n = 0

    def addWidget(self, w, *a):
        self._n += 1
        return self._n - 1

    def setCurrentIndex(self, i):
        self._i = i

    def currentIndex(self):
        return self._i


class FakeTabs(Dummy):
    def __init__(self, *a):
        self._t = []
        self._i = 0
        self.currentChanged = _Sig()

    def addTab(self, t):
        self._t.append(t)
        return len(self._t) - 1

    def setTabText(self, i, t):
        self._t[i] = t

    def tabText(self, i):
        return self._t[i]

    def currentIndex(self):
        return self._i

    def setCurrentIndex(self, i):
        self._i = i


class FakeMenu(Dummy):
    def addAction(self, *a):
        return FakeAction()


class FakeFileDialog(Dummy):
    path = ""

    @staticmethod
    def getSaveFileName(*a, **k):
        return FakeFileDialog.path, ""

    @staticmethod
    def getOpenFileName(*a, **k):
        return FakeFileDialog.path, ""

    @staticmethod
    def getExistingDirectory(*a, **k):
        return FakeFileDialog.path


class FakeClipboard(Dummy):
    text = None

    def setText(self, t):
        FakeClipboard.text = t


class FakeApp(Dummy):
    @staticmethod
    def instance():
        return None

    @staticmethod
    def clipboard():
        return FakeClipboard()

    @staticmethod
    def style():
        return Dummy()


class FakeIcon(Dummy):
    @staticmethod
    def fromTheme(name):
        d = Dummy()
        d.isNull = lambda: True
        return d


SPECIAL = {
    "QThread": QThread, "pyqtSignal": pyqtSignal, "QTreeWidgetItem": FakeItem,
    "QTreeWidget": FakeTree, "QComboBox": FakeCombo, "QLineEdit": FakeEdit,
    "QLabel": FakeLabel, "QCheckBox": FakeCheck, "QSpinBox": FakeSpin, "QDoubleSpinBox": FakeSpin,
    "QPlainTextEdit": FakeText, "QMenu": FakeMenu,
    "QFileDialog": FakeFileDialog, "QStackedWidget": FakeStack, "QTabBar": FakeTabs, "QApplication": FakeApp, "QIcon": FakeIcon,
}
NAMESPACES = {"Qt", "QStyle", "QPalette", "QMessageBox", "QFont", "QAbstractItemView",
              "QHeaderView", "QFrame", "QPainter", "QSizePolicy"}


def _mod(name):
    m = types.ModuleType(name)
    cache = {}

    def getattr_(n):
        if n.startswith("__"):
            raise AttributeError(n)
        if n not in cache:
            if n in SPECIAL:
                cache[n] = SPECIAL[n]
            elif n in NAMESPACES:
                cache[n] = NS()
            else:
                cache[n] = type(n, (Dummy,), {})
        return cache[n]

    m.__getattr__ = getattr_
    return m


def install():
    pkg = _mod("PyQt6")
    pkg.__path__ = []
    sys.modules["PyQt6"] = pkg
    for sub in ("QtCore", "QtGui", "QtWidgets"):
        m = _mod("PyQt6." + sub)
        sys.modules["PyQt6." + sub] = m
        setattr(pkg, sub, m)
