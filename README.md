# dbus-top

A simple tool to watch the amount of traffic on dbus.

## Requirements

This needs pyqt4. On a debian-type host you can install that with:

    apt-get install python-qt4 python-qt4-dbus

## Running against a remote dbus

You can run dbus-top against a remote dbus by using `socat`. On the remote
host, run this command:

    socat TCP-LISTEN:7272,reuseaddr,fork UNIX-CONNECT:/var/run/dbus/system_bus_socket

On the local host, map it back to a local socket:

    socat ABSTRACT-LISTEN:/tmp/ccgx,fork TCP:192.168.8.56:7272


Run dbus-top.py against this socket by setting it in the environment:

    DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/ccgx python dbus-top.py

Caveat: You have to run the process as a user with the same uid as the one
running socat on the remote end. On Venus this usually means `root`.

## Commandline options

 * `--summary`: Show only totals for each service and not for each path.
 * `--filter [prefix]`: Filter services by prefix. Defaults to com.victronenergy.
