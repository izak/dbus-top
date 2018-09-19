import sys
from time import time
from argparse import ArgumentParser
from PyQt4.QtCore import QObject, pyqtSlot, QTimer, QAbstractTableModel, QModelIndex, Qt, QVariant
from PyQt4.QtGui import QApplication, QTableView, QHeaderView
from PyQt4.QtDBus import QDBusConnection, QDBusMessage, QDBusInterface

class ServiceTable(QTableView):
    def __init__(self, *args):
        super(ServiceTable, self).__init__(*args)
        self.setSortingEnabled(True)

class Services(QAbstractTableModel):
    def __init__(self, m, summary, *args, **kwargs):
        super(Services, self).__init__(*args, **kwargs)
        self.servicemap = m
        self.summary = summary
        self.counts = []

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data)
        self.timer.start(5000)

    @pyqtSlot(QDBusMessage)
    def cb(self, msg):
        service = str(msg.service())
        if self.summary:
            path = "-"
        else:
            path = str(msg.path())
        name = self.servicemap.get(service, None)
        if name is not None:
            j = 0
            for j, item in enumerate(self.counts):
                if item[0] == name and item[1] == path:
                    item[2] += 1
                    self.dataChanged.emit(self.createIndex(j, 2), self.createIndex(j, 2))
                    break
            else:
                self.counts.append([name, path, 1, time()])
                self.rowsInserted.emit(QModelIndex(), j, j)

    def rowCount(self, parent=QModelIndex()):
        return len(self.counts)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def data(self, index, role=Qt.DisplayRole):
        row = index.row()
        col = index.column()

        v = self.counts[row]
        if role == Qt.DisplayRole:
            if col == 3: # rate
                interval = time() - v[3]
                return v[2]/interval if interval > 0 else 0
            else:
                return v[col]
        else:
            return QVariant()

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ["Service", "Path", "Count", "Frequency"][col]
        return QVariant()

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        if column == 3:
            now = time()
            self.counts = sorted(self.counts, key=lambda x: now-x[column],
                reverse=(order==Qt.DescendingOrder))
        else:
            self.counts = sorted(self.counts, key=lambda x: x[column],
                reverse=(order==Qt.DescendingOrder))
        self.layoutChanged.emit()

    def update_data(self):
        if len(self.counts):
            self.dataChanged.emit(self.createIndex(0, 3), self.createIndex(len(self.counts)-1, 3))


def main(args):
    parser = ArgumentParser(description=args[0])
    parser.add_argument('--summary',
        help="Show a per-service summary instead of path detail",
        action="store_true")
    parser.add_argument('--filter',
        help="Only show filters starting with this prefix",
        default="com.victronenergy.")
    cargs = parser.parse_args()

    app = QApplication(args)
    bus = QDBusConnection.sessionBus()

    # Get all services and build a service map
    iface = QDBusInterface("org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", bus)

    servicemap = {}
    names = iface.call("ListNames")
    for name in names.arguments()[0].toList():
        name = str(name.toString())
        if not name.startswith(cargs.filter):
            continue

        # Get the owner of the name
        owner = str(iface.call("GetNameOwner", name).arguments()[0].toString())
        servicemap[owner] = name

    services = Services(servicemap, cargs.summary)

    table = ServiceTable()
    table.setModel(services)
    table.resize(800, 600)
    table.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
    table.show()

    bus.connect("", "", "com.victronenergy.BusItem", "PropertiesChanged", services.cb)

    sys.exit(app.exec_())

if __name__=="__main__":
    main(sys.argv)
