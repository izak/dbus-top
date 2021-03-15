import sys
import os
import re
import subprocess
from time import time
from argparse import ArgumentParser
from itertools import count
from threading import Thread

import dbus

from PyQt5.QtCore import QObject, QTimer, QAbstractTableModel, QModelIndex, Qt, QVariant
from PyQt5.QtWidgets import QApplication, QTableView, QHeaderView

from dbus.mainloop.pyqt5 import DBusQtMainLoop

class MonitorThread(Thread):
    sender_re = re.compile(b' sender=([^ ;]*)')
    path_re = re.compile(b' path=([^ ;]*)')
    member_re = re.compile(b' member=([^ ;]*)')

    def __init__(self, cb, *args, **kwargs):
        super(MonitorThread, self).__init__(*args, **kwargs)
        self.cb = cb
        self.proc = None

    def run(self):
        self.proc = subprocess.Popen(['/usr/bin/dbus-monitor', '--session', 'interface=com.victronenergy.BusItem'],
            stdout=subprocess.PIPE, env={
                'DBUS_SESSION_BUS_ADDRESS': os.environ.get('DBUS_SESSION_BUS_ADDRESS', '')
        })
        line = self.proc.stdout.readline()
        while line:
            if line.startswith(b'signal ') or line.startswith(b'method call '):
                sender = self.sender_re.search(line)
                path = self.path_re.search(line)
                member = self.member_re.search(line)
                if sender and path and member:
                    sender = sender.group(1).strip()
                    path = path.group(1).strip()
                    member = member.group(1).strip()
                    self.cb(member.decode('ascii'), sender.decode('ascii'), path.decode('ascii'))

            # Next line
            line = self.proc.stdout.readline()

    def stop(self):
        self.proc.terminate()

class Service(list):
    _fields = dict(zip(("name", "path", "hits", "getvalue", "setvalue", "start"), count()))
    def __init__(self, *args):
        super(Service, self).__init__(args)

    def __getattr__(self, a):
        try:
            return self[self._fields[a]]
        except (KeyError, IndexError):
            raise AttributeError(a)

    def __setattr__(self, k, v):
        try:
            self[self._fields[k]] = v
        except (KeyError, IndexError):
            raise AttributeError(a)

class ServiceTable(QTableView):
    def __init__(self, *args):
        super(ServiceTable, self).__init__(*args)
        self.setSortingEnabled(True)

class Services(QAbstractTableModel):
    def __init__(self, m, p, summary, *args, **kwargs):
        super(Services, self).__init__(*args, **kwargs)
        self.servicemap = m
        self.processmap = p
        self.summary = summary
        self.counts = []

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data)
        self.timer.start(5000)

    def update_field(self, field, sender, path):
        name = self.servicemap.get(sender, None)
        if name is None:
            name = self.processmap.get(sender, None)
            name = "[      PID:{}      ]".format(name) if name else None
        if name is not None:
            j = 0
            for j, item in enumerate(self.counts):
                if item.name == name and item.path == path:
                    setattr(item, field, getattr(item, field) + 1)
                    idx = self.createIndex(j, item._fields[field])
                    self.dataChanged.emit(idx, idx)
                    break
            else:
                self.counts.append(Service(name, path, int(field=='hits'),
                    int(field=='getvalue'), int(field=='setvalue'), time()))
                self.rowsInserted.emit(QModelIndex(), j, j)

    def cb(self, member, sender, path):
        path = '-' if self.summary else path
        if member == 'PropertiesChanged':
            self.update_field('hits', sender, path)
        elif member == 'GetValue':
            self.update_field('getvalue', sender, path)
        elif member == 'SetValue':
            self.update_field('setvalue', sender, path)

    def rowCount(self, parent=QModelIndex()):
        return len(self.counts)

    def columnCount(self, parent=QModelIndex()):
        return 6

    def data(self, index, role=Qt.DisplayRole):
        row = index.row()
        col = index.column()

        v = self.counts[row]
        if role == Qt.DisplayRole:
            if col == 5: # rate
                interval = time() - v[col]
                return round(sum(v[2:5])/interval, 2) if interval > 0 else 0
            else:
                return v[col]
        else:
            return QVariant()

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ["Service", "Path", "PropertiesChanged", "GetValue", "SetValue", "Frequency"][col]
        return QVariant()

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        if column == 5:
            now = time()
            self.counts = sorted(self.counts, key=lambda x: now-x.start,
                reverse=(order==Qt.DescendingOrder))
        else:
            self.counts = sorted(self.counts, key=lambda x: x[column],
                reverse=(order==Qt.DescendingOrder))
        self.layoutChanged.emit()

    def update_data(self):
        if len(self.counts):
            self.dataChanged.emit(self.createIndex(0, 5), self.createIndex(len(self.counts)-1, 5))


def main(args):
    DBusQtMainLoop(set_as_default=True)

    parser = ArgumentParser(description=args[0])
    parser.add_argument('--summary',
        help="Show a per-service summary instead of path detail",
        action="store_true")
    parser.add_argument('--filter',
        help="Only show filters starting with this prefix",
        default="com.victronenergy.")
    cargs = parser.parse_args()

    app = QApplication(args)
    bus = dbus.SessionBus()

    list_names = lambda: [str(x) for x in bus.get_object("org.freedesktop.DBus",
         "/org/freedesktop/DBus").get_dbus_method("ListNames",
         dbus_interface="org.freedesktop.DBus")()]
    get_name_owner = lambda n: str(bus.get_name_owner(n))
    get_name_process = lambda n: int(bus.get_object("org.freedesktop.DBus",
        "/org/freedesktop/DBus").get_dbus_method("GetConnectionUnixProcessID",
        dbus_interface="org.freedesktop.DBus")(n))

    servicemap = {}
    processmap = {}
    for name in list_names():
        if name.startswith(':'):
            # What process is this tied to?
            pid = get_name_process(name)
            processmap[name] = pid
            continue
        if not name.startswith(cargs.filter):
            continue

        # Get the owner of the name
        owner = get_name_owner(name)
        servicemap[owner] = name

    services = Services(servicemap, processmap, cargs.summary)

    table = ServiceTable()
    table.setModel(services)
    table.resize(800, 600)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.show()

    # Use dbus-monitor to monitor things, because eavesdropping doesn't work and BecomeMonitor
    # runs into trouble with automatic replies in libdbus.
    monitor = MonitorThread(services.cb)
    monitor.start()
    r = app.exec_()
    monitor.stop()
    monitor.join()
    sys.exit(r)


if __name__=="__main__":
    main(sys.argv)
