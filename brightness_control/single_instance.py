"""One local Qt server per Windows user session, with a tiny command channel."""
import os
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    received = Signal(str)

    def __init__(self):
        super().__init__()
        # A fixed name is enough on Windows, where named pipes are scoped by
        # the active user's access token. PID would break detection.
        self.name = f'BrightnessVoiceControl-{os.environ.get("USERNAME", "user")}'
        self.server = QLocalServer(self)

    def acquire(self, command='panel') -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(300):
            socket.write(command.encode('ascii', errors='ignore'))
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            return False
        self.server.newConnection.connect(self._receive)
        if self.server.listen(self.name):
            return True
        # Another instance may have started during the short connect timeout.
        retry = QLocalSocket()
        retry.connectToServer(self.name)
        if retry.waitForConnected(500):
            retry.write(command.encode('ascii', errors='ignore'))
            retry.flush()
            retry.waitForBytesWritten(300)
            retry.disconnectFromServer()
        return False

    def _receive(self):
        while self.server.hasPendingConnections():
            peer = self.server.nextPendingConnection()
            if peer.waitForReadyRead(300):
                command = bytes(peer.readAll()).decode('ascii', errors='ignore')
                self.received.emit(command if command in ('panel', 'settings') else 'panel')
            peer.disconnectFromServer()
            peer.deleteLater()

    def close(self):
        self.server.close()
