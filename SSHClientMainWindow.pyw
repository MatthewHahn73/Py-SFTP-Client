"""
SSH Client GUI 

Authored by: Matthew Hahn
Github: https://github.com/MatthewHahn73/Py-SFTP-Client

Current Bugs
    -Progress bar in bottom left of the status bar is not aligned left properly at certain window resolutions
Current Issues
    -Not very effecient when moving lots of small files at once
        -Implement yield?
    -Strange stuttering after large transfer when resizing window
Future Features
    -Sort by folders first
    -Need to send a signal back to update the views when a new folder is created
    -Add in a confirmation prompt for deletions
    -Add in the ability to safely cancel an operation (Upload/Download)
    -Add in a sync directories button
        -Would ensure missing files in both active directories would be transferred to the other directory
    -Add in notification for failed/corrupt transfers 
    -Add in the option to connect via SSH certificates
    -Modify stylesheet to be more modern 

Required Software
    -Python 
        -Version >= 3.7
        -Installation: https://www.python.org/downloads/
    -Python Modules
        -PYQT6
            -Purpose: GUI Interface
            -Installation: https://pypi.org/project/PyQt6/
            -Documentation: https://www.riverbankcomputing.com/static/Docs/PyQt6/
        -paramiko 
            -Purpose: SSH Connections
            -Installation: https://pypi.org/project/paramiko/
            -Documentation - https://www.paramiko.org/
        -QLogHandler
            -Purpose: Custom QObject that handles log messages
            -Installation: Included (/Assets/Modules/)
        -QStandardItemModelCustom
            -Purpose: Custom QStandardItemModel that handles moving items from one QTreeView to another
            -Installation: Included (/Assets/Modules/)
        -QThreadWorker
            -Purpose: Custom QObject that handles paramiko calls on a seperate thread
            -Installation: Included (/Assets/Modules/)
        
Loaded GUI Resources (And structure)
    -MainWidget (QWidget)
        -VerticalStructureLayout (QVBoxLayout)
            -ConnectionCredentialsLayout (QHBoxLayout)
                -A_HostLayout (QHBoxLayout)
                    -A_HostLabel (QLabel)
                    -B_HostEdit (QLineEdit)
                -B_PortLayout (QHBoxLayout)
                    -A_PortLabel (QLabel)
                    -B_PortEdit (QLineEdit)
                -C_UsernameLayout (QHBoxLayout)
                    -A_UsernameLabel (QLabel)
                    -B_UsernameEdit (QLineEdit)
                -D_PasswordLayout (QHBoxLayout)
                    -A_PasswordLabel (QLabel)
                    -B_PasswordEdit (QLineEdit)
                -E_ConnectionButton (QPushButton)
            -FileStructureGrid (QGridLayout)
                -ConnectedDirHeaderLayout (QHBoxLayout)
                    -ConnectedCreateFolder (QPushButton)
                    -ConnectedDirEdit (QLineEdit)
                    -ConnectedHiddenToggleCheckbox (QCheckbox)
                    -ConnectedDirUpOne (QPushButton)
                    -ConnectedLabel (QLabel)
                    -ConnectedRefresh (QPushButton)
                -ConnectedMachineDirectoryTree (QTreeView)
                -CurrentDirHeaderLayout (QHBoxLayout)
                    -CurrentCreateFolder (QPushButton)
                    -CurrentDirEdit (QLineEdit)
                    -CurrentHiddenToggleCheckbox (QCheckbox)
                    -CurrentDirUpOne (QPushButton)
                    -CurrentLabel (QLabel)
                    -CurrentRefresh (QPushButton)
                -CurrentMachineDirectoryTree (QTreeView)
            -GeneralLog (QTextBrowser)
    -SMTPMenuBar (QMenuBar)
        -menuFile (QMenu)
            -actionClose (QAction)
        -menuHelp (QMenu)
            -actionAbout (QAction)
        -menuOptions (QMenu)
            -actionShow_Password (QAction)
            -menuLogging_Level (QAction)
                -actionDebugging (QAction)
                -actionError (QAction)
                -actionInfo (QAction)
                -actionWarning (QAction)
        -menuServer (QMenu)
            -actionDisconnect (QAction)
    -SMTPStatusBar (QStatusBar)
"""

import os, logging, sys, paramiko, platform, json, math, webbrowser, re
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtSvg import *
from PyQt6 import uic
from Assets.Modules import \
    QLogHandler as LogHanderObject \
    , QThreadWorker as ThreadWorkerObject \
    , QStandardItemModelCustom as StandardItemModelCustomObject \

#Constants
VERSIONNUMBER = "QTSFTP Client v1.0"
ERRORTEMPLATE = "A(n) {0} exception occurred. Arguments:\n{1!r}"
REPOSITORYLINK = "https://github.com/MatthewHahn73/Py-SFTP-Client"

#Main window
class SSHClientMainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi("Assets/GUI/SMTPClientGUI.ui", self)    #Load main GUI layout
        
        #Instantiate the SSH Object
        self.SSHObject = paramiko.SSHClient()   
        self.SSHObject.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        #Instantiate the secondary thread
        self.PThread = QThread(self) 

        #Set up the logger
        self.LogHandler = LogHanderObject.QLogHandler()
        self.LogHandler.appendPlainText.connect(self.GeneralLog.append)
        logging.getLogger().addHandler(self.LogHandler)
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("paramiko").setLevel(logging.WARNING)

        #Set up the status bar
        self.StatusBarLabel = QLabel("Disconnected")
        self.StatusBarLabel.setContentsMargins(5,0,0,0)
        self.SMTPStatusBar.addWidget(self.StatusBarLabel, 1)
        self.StatusBarProgressBar = QProgressBar()
        self.StatusBarProgressBar.setRange(0, 100)
        self.StatusBarProgressBar.setFixedSize(200, 25)
        self.SMTPStatusBar.addWidget(self.StatusBarProgressBar, 1)
        self.StatusBarProgressBar.hide()

        #Set menu item triggers
        self.actionClose.triggered.connect(self.close)
        self.actionDisconnect.triggered.connect(self.ExecuteDisconnectButton)
        self.actionShow_Password.triggered.connect(self.TogglePasswords)
        self.actionError.triggered.connect(lambda: self.ToggleLoggingLevel("Error"))
        self.actionWarning.triggered.connect(lambda: self.ToggleLoggingLevel("Warning"))
        self.actionInfo.triggered.connect(lambda: self.ToggleLoggingLevel("Info"))
        self.actionDebugging.triggered.connect(lambda: self.ToggleLoggingLevel("Debug"))
        self.actionAbout.triggered.connect(lambda: self.OpenWebBrowserLink(REPOSITORYLINK))

        #Set button triggers
        self.E_ConnectionButton.clicked.connect(self.ExecuteConnectButton)
        self.CurrentHiddenToggleCheckbox.clicked.connect(self.ExecuteShowCurrentHiddenFilesButton)
        self.CurrentDirUpOne.clicked.connect(self.ExecuteCurrentNavigateOneUpButton)
        self.ConnectedHiddenToggleCheckbox.clicked.connect(self.ExecuteShowConnectedHiddenFilesButton)
        self.ConnectedDirUpOne.clicked.connect(self.ExecuteConnectedNavigateOneUpButton)
        self.CurrentRefresh.clicked.connect(lambda: self.LoadGivenLocalDirectory(self.CurrentDirEdit.text()))
        self.ConnectedRefresh.clicked.connect(lambda: self.LoadGivenRemoteDirectory(self.ConnectedDirEdit.text()))
        self.CurrentCreateFolder.clicked.connect(self.ExecuteCurrentCreateFolder)
        self.ConnectedCreateFolder.clicked.connect(self.ExecuteConnectedCreateFolder)

        #Set the TextEdit triggers
        self.CurrentDirEdit.editingFinished.connect(lambda: self.LoadGivenLocalDirectory(self.CurrentDirEdit.text()))
        self.ConnectedDirEdit.editingFinished.connect(lambda: self.LoadGivenRemoteDirectory(self.ConnectedDirEdit.text()))

        #Set the tree triggers
        self.CurrentMachineDirectoryTree.doubleClicked.connect(self.CurrentItemDoubleClicked)
        self.CurrentMachineDirectoryTree.customContextMenuRequested.connect(self.CurrentContextMenuGenerated)

        self.ConnectedMachineDirectoryTree.doubleClicked.connect(self.ConnectedItemDoubleClicked)
        self.ConnectedMachineDirectoryTree.customContextMenuRequested.connect(self.ConnectedContextMenuGenerated)

        #Instantiate the custom QStandardItemModels for the trees
        self.CurrentDirectoryModel = StandardItemModelCustomObject.QStandardItemModelCustom("CurrentDirectoryModel")
        self.CurrentDirectoryModel.valueAdded.connect(self.CurrentDirectoryModelChanged)
        self.CurrentDirectoryModel.customItemChanged.connect(self.RenameLocalFile)

        self.ConnectedDirectoryModel = StandardItemModelCustomObject.QStandardItemModelCustom("ConnectedDirectoryModel")
        self.ConnectedDirectoryModel.valueAdded.connect(self.ConnectedDirectoryModelChanged)
        self.ConnectedDirectoryModel.customItemChanged.connect(self.RenameRemoteFile)
        
        #Set status label
        self.UpdateStatusLabel("Disconnected", "white")

        #Load in file extensions
        self.FileExtensionDict = self.ReturnFileExtensions()

        #Load home directory
        self.CurrentDirEdit.setText(QDir.homePath())
        self.LoadGivenLocalDirectory(self.CurrentDirEdit.text())

        #Set application icon 
        self.setWindowIcon(QIcon("Assets/Icons/Padlock_Icon.ico"))

    def ExecuteConnectButton(self):
        if not self.PThread.isRunning():
            self.UpdateStatusLabel("Disconnected", "white")
            self.PThread = QThread(self) 
            self.PWorker = ThreadWorkerObject.QThreadWorker (
                    SSHObj = self.SSHObject
                    , Conn = {
                        "Host": self.B_HostEdit.text()
                        , "Port": self.B_PortEdit.text()
                        , "Username": self.B_UsernameEdit.text()
                        , "Password": self.B_PasswordEdit.text()
                    }
                    , Misc = {
                        "File Extensions" : self.FileExtensionDict
                    }
                )
            self.PWorker.moveToThread(self.PThread)
            self.PThread.started.connect(self.PWorker.ConnectAndOpenSFTP)    
            self.PWorker.completeDataSignal.connect(self.ConnectionToServerResults)
            self.PThread.start()
        else:
            logging.warning("Cannot attempt connection to server while secondary thread is in use")

    def ExecuteDisconnectButton(self):
        if not self.PThread.isRunning():
            self.PThread = QThread(self) 
            self.PWorker = ThreadWorkerObject.QThreadWorker (
                    SSHObj = self.SSHObject
                )
            self.PWorker.moveToThread(self.PThread)
            self.PThread.started.connect(self.PWorker.DisconnectAndCloseSFTP)    
            self.PWorker.completeDataSignal.connect(self.DisconnectionToServerResults)
            self.PThread.start()
        else:
            logging.warning("Cannot attempt disconnection to server while secondary thread is in use")

    def LoadGivenLocalDirectory(self, Path):
        if not self.PThread.isRunning():
            self.PThread = QThread(self) 
            self.PWorker = ThreadWorkerObject.QThreadWorker (
                    Misc = {
                        "Local Path": Path
                        , "File Extensions" : self.FileExtensionDict
                    }
                )
            self.PWorker.moveToThread(self.PThread)
            self.PThread.started.connect(self.PWorker.QueryDirectoriesContentsLocalRequest)    
            self.PWorker.completeDataSignal.connect(self.LocalQueryResults)
            self.PThread.start()
        else:
            logging.warning("Cannot query for the local directory while the secondary thread is in use")
        
    def LoadGivenRemoteDirectory(self, Path):
        if not self.PThread.isRunning():
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is not None and SSHTransport.is_active()) and not (self.SFTPObject.sock.closed):
                self.PThread = QThread(self) 
                self.PWorker = ThreadWorkerObject.QThreadWorker (
                        SSHObj = self.SSHObject
                        , SFTPObj = self.SFTPObject
                        , Misc = {
                            "Server Path": Path
                            , "File Extensions" : self.FileExtensionDict
                        }
                    )
                self.PWorker.moveToThread(self.PThread)
                self.PThread.started.connect(self.PWorker.QueryDirectoriesContentsServerRequest)    
                self.PWorker.completeDataSignal.connect(self.ServerQueryResults)
                self.PThread.start()
            else:
                logging.warning("Cannot fetch the remote directory without an active SSH connection")
        else:
            logging.warning("Cannot query for the remote directory while the secondary thread is in use")

    def ExecuteCurrentCreateFolder(self):
        if not self.PThread.isRunning():
            self.PThread = QThread(self) 
            self.PWorker = ThreadWorkerObject.QThreadWorker (
                    Misc = {
                        "Local Path": self.CurrentDirEdit.text()
                        , "File Extensions" : self.FileExtensionDict
                    }
                )
            self.PWorker.moveToThread(self.PThread)
            self.PThread.started.connect(self.PWorker.CreateFolderCurrentDirectoryRequest)  
            self.PWorker.serverMessage.connect(self.ServerUpdateMessage)
            self.PWorker.completeDataSignal.connect(self.LocalQueryResults)
            self.PThread.start()
        else:
            logging.warning("Cannot create folder for the current directory while the secondary thread is in use")

    def ExecuteConnectedCreateFolder(self):
        if not self.PThread.isRunning():
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is not None and SSHTransport.is_active()) and not (self.SFTPObject.sock.closed):
                self.PThread = QThread(self) 
                self.PWorker = ThreadWorkerObject.QThreadWorker (
                        SSHObj = self.SSHObject
                        , SFTPObj = self.SFTPObject
                        , Misc = {
                            "Server Path": self.ConnectedDirEdit.text()
                            , "File Extensions" : self.FileExtensionDict
                        }
                    )
                self.PWorker.moveToThread(self.PThread)
                self.PThread.started.connect(self.PWorker.CreateFolderRemoteDirectoryRequest)   
                self.PWorker.completeDataSignal.connect(self.ServerQueryResults)
                self.PThread.start()
            else:
                logging.warning("Cannot create folder for the connected directory without an active SFTP connection")
        else:
            logging.warning("Cannot create folder for the connected directory while the secondary thread is in use")

    def ExecuteTransferringFiles(self, Type, TransferData):
        if not self.PThread.isRunning():
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is not None and SSHTransport.is_active()) and not (self.SFTPObject.sock.closed):
                self.PThread = QThread(self) 
                self.PWorker = ThreadWorkerObject.QThreadWorker (
                        SSHObj = self.SSHObject
                        , SFTPObj = self.SFTPObject
                        , Misc = {
                            "Transfer Type" : Type
                            , "Transfer Data": TransferData
                            , "Local Path": self.CurrentDirEdit.text()
                            , "Server Path": self.ConnectedDirEdit.text()
                            , "File Extensions" : self.FileExtensionDict
                        }
                    )
                self.PWorker.moveToThread(self.PThread)
                self.PThread.started.connect(self.PWorker.TransferFilesServerRequest)  
                self.PWorker.serverMessage.connect(self.ServerUpdateMessage)
                self.PWorker.transferProgress.connect(self.FileTransferProgress)
                self.PWorker.transferCompleteLocal.connect(self.LocalQueryResults)
                self.PWorker.transferCompleteRemote.connect(self.ServerQueryResults)
                self.PWorker.completeDataSignal.connect(self.FileTransferCompleted)
                self.PThread.start()
            else:
                logging.warning("Cannot transfer files without an active SFTP connection")
        else:
            logging.warning("Cannot transfer files while the secondary thread is in use")

    def RenameRemoteFile(self, Index, Role, OldValue, NewValue):
        if not self.PThread.isRunning():
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is not None and SSHTransport.is_active()) and not (self.SFTPObject.sock.closed):
                self.PThread = QThread(self) 
                self.PWorker = ThreadWorkerObject.QThreadWorker (
                        SSHObj = self.SSHObject
                        , SFTPObj = self.SFTPObject
                        , Misc = {
                            "Old Name": os.path.join(self.ConnectedDirEdit.text(), OldValue)
                            , "New Name": os.path.join(self.ConnectedDirEdit.text(), NewValue)
                            , "Server Path" : self.ConnectedDirEdit.text()
                            , "File Extensions" : self.FileExtensionDict
                        }
                    )
                self.PWorker.moveToThread(self.PThread)
                self.PThread.started.connect(self.PWorker.RenameFileOrDirectory)  
                self.PWorker.completeDataSignal.connect(self.ServerFileRenamingCompleted)
                self.PThread.start()
            else:
                logging.warning("Cannot rename server files without an active SFTP connection")
        else:
            logging.warning("Cannot rename files on the server while the secondary thread is in use")

    def DeleteRemoteFiles(self, Items):
        if not self.PThread.isRunning():
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is not None and SSHTransport.is_active()) and not (self.SFTPObject.sock.closed):
                self.PThread = QThread(self) 
                self.PWorker = ThreadWorkerObject.QThreadWorker (
                        SSHObj = self.SSHObject
                        , SFTPObj = self.SFTPObject
                        , Misc = {
                            "Server Path": self.ConnectedDirEdit.text()
                            , "Directory Items" : Items
                            , "File Extensions" : self.FileExtensionDict
                        }
                    )
                self.PWorker.moveToThread(self.PThread)
                self.PThread.started.connect(self.PWorker.DeleteFileOrDirectoryServerRequest)              
                self.PWorker.serverMessage.connect(self.ServerUpdateMessage)
                self.PWorker.completeDataSignal.connect(self.ServerFileorDirectoryDeleteCompleted)
                self.PThread.start()
            else:
                logging.warning("Cannot delete server files without an active SFTP connection")
        else:
            logging.warning("Cannot delete files on the server while the secondary thread is in use")

    def RenameLocalFile(self, Index, Role, OldValue, NewValue):
        if NewValue.strip() != OldValue.strip():
            OldPath = os.path.join(self.CurrentDirEdit.text(), OldValue)
            NewPath = os.path.join(self.CurrentDirEdit.text(), NewValue)
            os.rename(OldPath, NewPath)
            self.LoadGivenLocalDirectory(self.CurrentDirEdit.text()) 
            logging.info(f"Local file successfully renamed '{OldPath}' → '{NewPath}'")

    def DeleteLocalFiles(self, Path):
        if os.path.isdir(Path):
            for PathItem in os.listdir(Path):
                self.DeleteLocalFiles(os.path.join(Path, PathItem)) 
            os.rmdir(Path)
            logging.info(f"Local directory successfully deleted '{Path}'")
        elif os.path.isfile(Path):
            os.remove(Path)
            logging.info(f"Local file successfully deleted '{Path}'")

    def ExecuteShowCurrentHiddenFilesButton(self):
        Checked = self.CurrentHiddenToggleCheckbox.isChecked()
        CurrentDir = QDir.currentPath()
        ChangedIconPath = f"{CurrentDir}/Assets/Icons/view-visible.svg" if Checked else f"{CurrentDir}/Assets/Icons/view-hidden.svg"
        if not self.PThread.isRunning():
            self.CurrentHiddenToggleCheckbox.setIcon(QIcon(ChangedIconPath))
            self.LoadGivenLocalDirectory(self.CurrentDirEdit.text()) 
        else:
            logging.warning(f"Cannot fetch local directory while secondary thread is active")
            self.CurrentHiddenToggleCheckbox.setChecked(not Checked)

    def ExecuteShowConnectedHiddenFilesButton(self):
        Checked = self.ConnectedHiddenToggleCheckbox.isChecked()
        ConnectedDir = QDir.currentPath()
        ChangedIconPath = f"{ConnectedDir}/Assets/Icons/view-visible.svg" if Checked else f"{ConnectedDir}/Assets/Icons/view-hidden.svg"
        if not self.PThread.isRunning():
            self.ConnectedHiddenToggleCheckbox.setIcon(QIcon(ChangedIconPath))
            self.LoadGivenRemoteDirectory(self.ConnectedDirEdit.text()) 
        else:
            logging.warning(f"Cannot fetch local directory while secondary thread is active")
            self.ConnectedHiddenToggleCheckbox.setChecked(not Checked)

    def ExecuteCurrentNavigateOneUpButton(self): 
        OneDirectoryUp = os.path.dirname(self.CurrentDirEdit.text())
        if os.path.isdir(OneDirectoryUp):
            self.LoadGivenLocalDirectory(OneDirectoryUp) 

    def ExecuteConnectedNavigateOneUpButton(self):
        OneDirectoryUp = os.path.dirname(self.ConnectedDirEdit.text())
        self.LoadGivenRemoteDirectory(OneDirectoryUp) 

    def CurrentItemDoubleClicked(self, index):
        if index.isValid():
            PathIndex = index.sibling(index.row(), 0)
            ItemName = PathIndex.data()
            FullPath = os.path.join(self.CurrentDirEdit.text(), ItemName)
            if os.path.exists(FullPath):
                self.LoadGivenLocalDirectory(FullPath)
        
    def ConnectedItemDoubleClicked(self, index):
        if index.isValid():
            PathIndex = index.sibling(index.row(), 0)
            ItemName = PathIndex.data()
            FullPath = os.path.join(self.ConnectedDirEdit.text(), ItemName)
            self.LoadGivenRemoteDirectory(FullPath)

    def CurrentContextMenuGenerated(self, position):
        ItemSelectedIndex = self.CurrentMachineDirectoryTree.indexAt(position) 
        AllItemSelectedIndexes = [Index for Index in self.CurrentMachineDirectoryTree.selectionModel().selectedIndexes() if Index.column() == 0]
        if ItemSelectedIndex.isValid() and AllItemSelectedIndexes:
            #Create menu items 
            CurrentContextMenu = QMenu()
            UploadAction = CurrentContextMenu.addAction("Upload")
            CurrentContextMenu.addSeparator()
            RenameAction = CurrentContextMenu.addAction("Rename")
            DeleteAction = CurrentContextMenu.addAction("Delete")

            #Set menu item values to variables
            AllItemAttributes = []
            for Item in AllItemSelectedIndexes:
                AllItemAttributes.append({
                    "Origin View" : "CurrentDirectoryModel"
                    , "Item Name" : Item.siblingAtColumn(0).data()
                    , "Item Type" : Item.siblingAtColumn(1).data()
                    , "Item Size" : Item.siblingAtColumn(2).data()
                    , "Item Date" : Item.siblingAtColumn(3).data()
                })

            RenameAction.setEnabled(len(AllItemSelectedIndexes) == 1)
            MenuItemExecuted = CurrentContextMenu.exec(self.CurrentMachineDirectoryTree.viewport().mapToGlobal(position))

            #Context menu item selected logic
            if MenuItemExecuted == UploadAction:
                self.ExecuteTransferringFiles("Upload", AllItemAttributes)
            elif MenuItemExecuted == RenameAction:
                self.CurrentMachineDirectoryTree.edit(AllItemSelectedIndexes[0].siblingAtColumn(0)) 
            elif MenuItemExecuted == DeleteAction:
                for Item in AllItemAttributes:
                    self.DeleteLocalFiles(os.path.join(self.CurrentDirEdit.text(), Item["Item Name"]))
                self.LoadGivenLocalDirectory(self.CurrentDirEdit.text()) 
                
    def ConnectedContextMenuGenerated(self, position):
        ItemSelectedIndex = self.ConnectedMachineDirectoryTree.indexAt(position) 
        AllItemSelectedIndexes = [Index for Index in self.ConnectedMachineDirectoryTree.selectionModel().selectedIndexes() if Index.column() == 0]
        if ItemSelectedIndex.isValid() and AllItemSelectedIndexes:
            #Create menu items 
            ConnectedContextMenu = QMenu()
            DownloadAction = ConnectedContextMenu.addAction("Download")
            ConnectedContextMenu.addSeparator()
            RenameAction = ConnectedContextMenu.addAction("Rename")
            DeleteAction = ConnectedContextMenu.addAction("Delete")

            #Set menu item values to variables
            AllItemAttributes = []
            for Item in AllItemSelectedIndexes:
                AllItemAttributes.append({
                    "Origin View" : "ConnectedDirectoryModel"
                    , "Item Name" : Item.siblingAtColumn(0).data()
                    , "Item Type" : Item.siblingAtColumn(1).data()
                    , "Item Size" : Item.siblingAtColumn(2).data()
                    , "Item Date" : Item.siblingAtColumn(3).data()
                })

            RenameAction.setEnabled(len(AllItemSelectedIndexes) == 1)
            MenuItemExecuted = ConnectedContextMenu.exec(self.ConnectedMachineDirectoryTree.viewport().mapToGlobal(position))

            #Context menu item selected logic
            if MenuItemExecuted == DownloadAction:
                self.ExecuteTransferringFiles("Download", AllItemAttributes)
            elif MenuItemExecuted == RenameAction:
                self.ConnectedMachineDirectoryTree.edit(AllItemSelectedIndexes[0].siblingAtColumn(0))   
            elif MenuItemExecuted == DeleteAction:
                self.DeleteRemoteFiles(AllItemAttributes)

    def ToggleLoggingLevel(self, Level):
        self.actionError.setChecked(False)
        self.actionInfo.setChecked(False)
        self.actionWarning.setChecked(False)
        self.actionDebugging.setChecked(False)
        if Level == "Info":
            self.actionInfo.setChecked(True)
            logging.getLogger("paramiko").setLevel(logging.INFO)
        elif Level == "Warning":
            self.actionWarning.setChecked(True)
            logging.getLogger("paramiko").setLevel(logging.WARNING)
        elif Level == "Error":
            self.actionError.setChecked(True)
            logging.getLogger("paramiko").setLevel(logging.ERROR)
        elif Level == "Debug":
            self.actionDebugging.setChecked(True)
            logging.getLogger("paramiko").setLevel(logging.DEBUG)

    def TogglePasswords(self):
        self.B_PasswordEdit.setEchoMode(QLineEdit.EchoMode.Password \
                                        if self.B_PasswordEdit.echoMode() == QLineEdit.EchoMode.Normal \
                                            else QLineEdit.EchoMode.Normal)
            
    def UpdateStatusLabel(self, Message, Color):
        self.StatusBarLabel.setText(Message)
        self.StatusBarLabel.setStyleSheet(f"color: {Color};")

    def IncludesErrors(self, Value):
        if "Error Thrown" in Value:
            return True
        return False

    def ReturnFileExtensions(self):
        try:
            with open("Assets/Files/FileExtensions.json") as File:
                return json.load(File)
        except Exception as e:
            logging.error(ERRORTEMPLATE.format(type(Error).__name__, Error.args)) 

    def ReturnFileIcon(self, FileType):
        if "Folder" in FileType: 
            return "Assets/Icons/Representations/folder-representation.svg"
        if FileType in list(self.FileExtensionDict.values()):
            ParsedFileType = FileType.replace(" ", "-").lower()
            #return f"Assets/Icons/{ParsedFileType}-representation.svg"
        return f"Assets/Icons/Representations/file-representation.svg"

    def ReturnHiddenItem(self, ItemPath):        
        if platform.system() != "Windows":  #Linux
            return os.path.basename(os.path.abspath(ItemPath)).startswith('.')
        return False 

    def OpenWebBrowserLink(self, Link):
        webbrowser.open(Link) 

    def closeEvent(self, event):
        logging.getLogger().removeHandler(self.LogHandler)
        del self.LogHandler

    @pyqtSlot(object)
    def CurrentDirectoryModelChanged(self, params):
        try:
            if not self.IncludesErrors(params):   
                ItemsObject = json.loads(params["Items"])
                OriginView = ItemsObject[0]["Origin View"]
                if OriginView == "CurrentDirectoryModel":
                    raise FileExistsError(f"Item(s) already exist in '{self.CurrentDirEdit.text()}'")
                else:
                    if not self.PThread.isRunning():
                        self.ExecuteTransferringFiles("Download", ItemsObject)
                    else: 
                        logging.warning("Cannot start a new transfer while another process is active")
            else:
                raise params["Error Thrown"]
        except FileExistsError as ExistsError:
            logging.warning(ExistsError) 
        except Exception as Error: 
            logging.error(ERRORTEMPLATE.format(type(Error).__name__, Error.args)) 

    @pyqtSlot(object)
    def ConnectedDirectoryModelChanged(self, params):
        try:
            if not self.IncludesErrors(params):   
                ItemsObject = json.loads(params["Items"])
                OriginView = ItemsObject[0]["Origin View"]
                if OriginView == "ConnectedDirectoryModel":
                    raise FileExistsError(f"Item(s) already exist in '{self.ConnectedDirEdit.text()}'")
                else:
                    if not self.PThread.isRunning():
                        self.ExecuteTransferringFiles("Upload", ItemsObject)
                    else: 
                        logging.warning("Cannot start a new transfer while another process is active")
            else:
                raise params["Error Thrown"]
        except FileExistsError as ExistsError:
            logging.warning(ExistsError) 
        except Exception as Error: 
            logging.error(ERRORTEMPLATE.format(type(Error).__name__, Error.args)) 

    @pyqtSlot(object)
    def ConnectionToServerResults(self, params):
        try:
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params):   
                self.SSHObject, self.SFTPObject = params["SSH Object"], params["SFTP Object"]
                SSHTransport = self.SSHObject.get_transport()
                if (SSHTransport is not None and SSHTransport.is_active()) and not (self.SFTPObject.sock.closed):
                    self.actionDisconnect.setEnabled(True)
                    TransportInfo = self.SSHObject.get_transport().getpeername()
                    self.UpdateStatusLabel(f"Connected to {TransportInfo[0]}:{TransportInfo[1]}", "#2bfb75")
                    logging.info(f"SSH connection successful to {TransportInfo[0]} on port {TransportInfo[1]}")
                    self.ServerQueryResults({
                        "Server Path" : params["Server Path"]
                        , "Directory Items" : params["Directory Items"]
                    })
                else:
                    raise Exception("SSH/SFTP connection could not be estasblished")
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def DisconnectionToServerResults(self, params):
        try:
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params):   
                self.SSHObject = params["SSH Object"]
                SSHTransport = self.SSHObject.get_transport()
                if SSHTransport is None or not SSHTransport.is_active():
                    self.actionDisconnect.setEnabled(False)
                    self.ConnectedMachineDirectoryTree.setModel(None)
                    self.ConnectedDirEdit.setText("")
                    self.UpdateStatusLabel("Disconnected", "white")
                    logging.info("SSH session closed")
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def LocalQueryResults(self, params):
        try:
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params):   
                ShowHidden, LocalPath, DirectoryItemsList = self.CurrentHiddenToggleCheckbox.isChecked(), params["Local Path"], params["Directory Items"]
                self.CurrentDirectoryModel.clear() 
                self.CurrentDirectoryModel.setHorizontalHeaderLabels(["Name", "Type", "File Size", "Date Modified"])
                for DirectoryItem in DirectoryItemsList:
                    DirectoryItemPath = os.path.join(LocalPath, DirectoryItem["Item Name"])
                    IsHiddenItem = self.ReturnHiddenItem(DirectoryItemPath)
                    if (not IsHiddenItem) or (IsHiddenItem and self.CurrentHiddenToggleCheckbox.isChecked()):
                        ItemName, ItemType, ItemSize, ItemModified = DirectoryItem["Item Name"], DirectoryItem["Item Type"], DirectoryItem["Item Size"], DirectoryItem["Item Date"]
                        if ItemName != None:
                            ItemNameObject = QStandardItem(ItemName)
                            ItemNameIcon = QIcon(self.ReturnFileIcon(ItemType))
                            ItemNameObject.setIcon(ItemNameIcon)
                            DirectoryItemRow = [ItemNameObject, QStandardItem(ItemType), QStandardItem(ItemSize), QStandardItem(ItemModified)]
                            self.CurrentDirectoryModel.appendRow(DirectoryItemRow)
                self.CurrentMachineDirectoryTree.setModel(self.CurrentDirectoryModel)
                self.CurrentMachineDirectoryTree.header().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
                self.CurrentMachineDirectoryTree.header().resizeSections(QHeaderView.ResizeMode.ResizeToContents)
                self.CurrentDirEdit.setText(LocalPath)
                self.CurrentDirUpOne.setEnabled(self.CurrentDirEdit.text() != '/')
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def ServerQueryResults(self, params):
        try:
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params):   
                ShowHidden, ServerPath, DirectoryItemsList = self.ConnectedHiddenToggleCheckbox.isChecked(), params["Server Path"], params["Directory Items"]
                self.ConnectedDirectoryModel.clear() 
                self.ConnectedDirectoryModel.setHorizontalHeaderLabels(["Name", "Type", "File Size", "Date Modified"])
                for DirectoryItem in DirectoryItemsList:
                    DirectoryItemPath = os.path.join(ServerPath, DirectoryItem["Item Name"])
                    IsHiddenItem = self.ReturnHiddenItem(DirectoryItemPath)
                    if (not IsHiddenItem) or (IsHiddenItem and ShowHidden):
                        ItemName, ItemType, ItemSize, ItemModified = DirectoryItem["Item Name"], DirectoryItem["Item Type"], DirectoryItem["Item Size"], DirectoryItem["Item Date"]
                        if ItemName != None:
                            ItemNameObject = QStandardItem(ItemName)
                            ItemNameIcon = QIcon(self.ReturnFileIcon(ItemType))
                            ItemNameObject.setIcon(ItemNameIcon)
                            DirectoryItemRow = [ItemNameObject, QStandardItem(ItemType), QStandardItem(ItemSize), QStandardItem(ItemModified)]
                            self.ConnectedDirectoryModel.appendRow(DirectoryItemRow)
                self.ConnectedMachineDirectoryTree.setModel(self.ConnectedDirectoryModel)
                self.ConnectedMachineDirectoryTree.header().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
                self.ConnectedMachineDirectoryTree.header().resizeSections(QHeaderView.ResizeMode.ResizeToContents)
                self.ConnectedDirEdit.setText(ServerPath)
                self.ConnectedDirUpOne.setEnabled(self.ConnectedDirEdit.text() != '/')
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def ServerFileRenamingCompleted(self, params):
        try:
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params):
                if params["Old Name"] != params["New Name"]:
                    self.ServerQueryResults({
                        "Server Path" : params["Server Path"]
                        , "Directory Items" : params["Server Results"]
                    })
                    logging.info(f"Server file successfully renamed '{params["Old Name"]}' → '{params["New Name"]}'")
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def ServerFileorDirectoryDeleteCompleted(self, params):
        try:
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params):
                self.ServerQueryResults({
                    "Server Path" : params["Server Path"]
                    , "Directory Items" : params["Server Results"]
                })
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def ServerUpdateMessage(self, params):
        try:
            if not self.IncludesErrors(params):
                logging.info(params["Message"])
                if "Item Size" in params:
                    if self.StatusBarProgressBar.isHidden():
                        self.StatusBarProgressBar.show()
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object) 
    def FileTransferProgress(self, params):
        try:
            if not self.IncludesErrors(params):
                ProgressPercentage = math.floor((params["Current Bytes"] / params["Total Bytes"]) * 100)
                self.StatusBarProgressBar.setValue(ProgressPercentage)
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

    @pyqtSlot(object)
    def FileTransferCompleted(self, params):
        try:
            self.StatusBarProgressBar.hide()
            if self.PThread.isRunning():
                self.PThread.quit()
            if not self.IncludesErrors(params): 
                self.LocalQueryResults({
                    "Local Path" : params["Local Path"]
                    , "Directory Items" : params["Local Results"]
                })
                self.ServerQueryResults({
                    "Server Path" : params["Server Path"]
                    , "Directory Items" : params["Server Results"]
                })
                logging.info(f"All file(s) successfully transferred. Runtime: {params["Runtime"]} second(s)")
            else:
                raise params["Error Thrown"]
        except Exception as E:
            logging.error(ERRORTEMPLATE.format(type(E).__name__, E.args)) 

if __name__ == "__main__":
    StylesheetPath = (os.path.dirname(os.path.realpath(__file__)) + "/Assets/Stylesheets/Dark_Theme.css").replace("\\", "/")
    if not os.path.exists(StylesheetPath): 
        logging.warning("Stylesheet Path: " + StylesheetPath + " could not be located")
    else:
        with open(StylesheetPath) as Stylesheet:
            app = QApplication(sys.argv)
            app.setStyleSheet(Stylesheet.read())
            Main = SSHClientMainWindow()
            #Main.showMaximized()
            Main.setWindowTitle(VERSIONNUMBER)
            Main.show()
            sys.exit(app.exec())