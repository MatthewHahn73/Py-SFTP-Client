from PyQt6.QtCore import *
import datetime, stat, os, time

class QThreadWorker(QObject):
    serverMessage = pyqtSignal(object)
    deleteCompleted = pyqtSignal(object)
    transferProgress = pyqtSignal(object)
    transferCompleteLocal = pyqtSignal(object)
    transferCompleteRemote = pyqtSignal(object)
    completeDataSignal = pyqtSignal(object)

    def __init__(self, SSHObj = None, SFTPObj = None, Conn = None, Misc = None):
        super().__init__()
        self.SSHObject = SSHObj
        self.SFTPObject = SFTPObj
        self.ConnectionParameters = Conn
        self.MiscParameters = Misc
        self.CancelCalled = False

    def ConnectAndOpenSFTP(self):
        try:
            self.SSHObject.connect(self.ConnectionParameters["Host"], self.ConnectionParameters["Port"], self.ConnectionParameters["Username"], self.ConnectionParameters["Password"])
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is not None and SSHTransport.is_active()):
                self.SFTPObject = self.SSHObject.open_sftp()
                stdin, stdout, stderr = self.SSHObject.exec_command("pwd")   #Attempt to fetch the default ssh directory path
                ServerErrorOuput = stderr.read().decode().strip()
                if not ServerErrorOuput:
                    RemoteDefaultDirectory = stdout.read().decode().strip()
                    QueryResults = self.QueryForADirectoriesContentsRemote(RemoteDefaultDirectory, self.MiscParameters["File Extensions"])
                    self.completeDataSignal.emit({
                        "SSH Object" : self.SSHObject
                        , "SFTP Object" : self.SFTPObject
                        , "Server Path" : RemoteDefaultDirectory
                        , "Directory Items" : QueryResults
                    })
                else: 
                    raise Exception(ServerErrorOuput)
            else:
                raise Exception(f"Unable to connect to {self.ConnectionParameters["Host"]} on port {self.ConnectionParameters["Port"]}")
        except Exception as e:
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def DisconnectAndCloseSFTP(self):
        try:
            if self.SFTPObject is not None:
                self.SFTPObject.close()
            self.SSHObject.close()
            SSHTransport = self.SSHObject.get_transport()
            if (SSHTransport is None or not SSHTransport.is_active()):
                self.completeDataSignal.emit({
                    "SSH Object" : self.SSHObject
                    , "SFTP Object" : self.SFTPObject
                })
            else:
                raise Exception(f"Unable to safely disconnect from the server")
        except Exception as e:
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def QueryDirectoriesContentsLocalRequest(self):
        try:
            QueryResults = self.QueryForADirectoriesContentsLocal(self.MiscParameters["Local Path"], self.MiscParameters["File Extensions"])
            if (type(QueryResults) == list):
                self.completeDataSignal.emit({
                    "Local Path" : self.MiscParameters["Local Path"] 
                    , "Directory Items" : QueryResults
                })
            else:
                raise QueryResults
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def QueryForADirectoriesContentsLocal(self, LocalPath, FileExtensions):
        if not os.path.isdir(LocalPath):
            return Exception(f"Cannot navigate to '{LocalPath}'. It is a file")
        else:
            DirectoryItems = os.listdir(LocalPath)
            DirectoryItemList = []
            for DirectoryItem in os.listdir(LocalPath):
                DirectoryItemPath = os.path.join(LocalPath, DirectoryItem)
                ItemType, ItemSize = "", -1
                if os.path.exists(DirectoryItemPath):
                    if os.path.isfile(DirectoryItemPath):
                        ItemType = self.ReturnFileExtension(DirectoryItemPath, FileExtensions)
                        ItemSize = self.ReturnReadableFileSize(os.path.getsize(DirectoryItemPath))
                    elif os.path.isdir(DirectoryItemPath):
                        ItemType = "Folder"
                        ItemSize = ""
                    DirectoryItemList.append({
                        "Item Name" : os.path.basename(DirectoryItemPath)
                        , "Item Type" : ItemType
                        , "Item Size" : ItemSize
                        , "Item Date" : str(datetime.datetime.fromtimestamp(os.stat(DirectoryItemPath).st_mtime).strftime('%Y-%m-%d %I:%M %p'))
                    })
            return DirectoryItemList

    def QueryDirectoriesContentsServerRequest(self):
        try:
            QueryResults = self.QueryForADirectoriesContentsRemote(self.MiscParameters["Server Path"], self.MiscParameters["File Extensions"])
            if (type(QueryResults) == list):
                self.completeDataSignal.emit({
                    "Server Path" : self.MiscParameters["Server Path"]
                    , "Directory Items" : QueryResults
                })
            else:
                raise QueryResults
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def QueryForADirectoriesContentsRemote(self, ServerPath, FileExtensions):
        PathAttributes = self.SFTPObject.lstat(ServerPath)
        if stat.S_ISREG(PathAttributes.st_mode):
            return Exception(f"Cannot navigate to '{ServerPath}'. It is a file")
        else:
            DirectoryItemList = []
            for DirectoryItem in self.SFTPObject.listdir_attr(ServerPath): 
                DirectoryItemPath = os.path.join(ServerPath, DirectoryItem.filename)
                ItemType, ItemSize = "", -1
                if stat.S_ISREG(DirectoryItem.st_mode):     #File
                    ItemType = self.ReturnFileExtension(DirectoryItemPath, FileExtensions)
                    ItemSize = self.ReturnReadableFileSize(DirectoryItem.st_size)
                elif stat.S_ISDIR(DirectoryItem.st_mode):   #Directory
                    ItemType = "Folder"
                    ItemSize = ""
                elif stat.S_ISLNK(DirectoryItem.st_mode):   #Symbolic Directory
                    ItemType = "Folder (Symlink)"
                    ItemSize = ""
                DirectoryItemList.append({
                    "Item Name" : DirectoryItem.filename
                    , "Item Type" : ItemType
                    , "Item Size" : ItemSize
                    , "Item Date" : str(datetime.datetime.fromtimestamp(DirectoryItem.st_mtime).strftime('%Y-%m-%d %I:%M %p'))
                })
            return DirectoryItemList
            
    def RenameFileOrDirectory(self):
        try:
            if self.MiscParameters["Old Name"] != self.MiscParameters["New Name"]:
                self.SFTPObject.rename(self.MiscParameters["Old Name"], self.MiscParameters["New Name"])
                QueryResults = self.QueryForADirectoriesContentsRemote(self.MiscParameters["Server Path"], self.MiscParameters["File Extensions"])
                if (type(QueryResults) == list):
                    self.completeDataSignal.emit({
                        "Old Name" : self.MiscParameters["Old Name"]
                        , "New Name" : self.MiscParameters["New Name"]
                        , "Server Path" : self.MiscParameters["Server Path"]
                        , "Server Results" : QueryResults
                    })        
                else:
                    raise QueryResults
            else: 
                self.completeDataSignal.emit({
                    "Old Name" : self.MiscParameters["Old Name"]
                    , "New Name" : self.MiscParameters["New Name"]
                })        
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def DeleteFileOrDirectoryServerRequest(self):
        try:
            StartTime = time.time()
            for Item in self.MiscParameters["Directory Items"]:
                self.DeleteFileOrDirectory(os.path.join(self.MiscParameters["Server Path"], Item["Item Name"]))
            QueryResults = self.QueryForADirectoriesContentsRemote(self.MiscParameters["Server Path"], self.MiscParameters["File Extensions"])
            if (type(QueryResults) == list):
                self.completeDataSignal.emit({
                    "Server Path" : self.MiscParameters["Server Path"]
                    , "Server Results" : QueryResults
                    , "Runtime" : round((time.time() - StartTime), 2)
                })
            else:
                raise QueryResults
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def DeleteFileOrDirectory(self, Path):
        if not self.CancelSignal:
            if self.ReturnRemoteDirectory(Path):
                for PathItem in self.SFTPObject.listdir(Path):
                    self.DeleteFileOrDirectory(os.path.join(Path, PathItem)) 
                self.SFTPObject.rmdir(Path)
                self.serverMessage.emit({
                    "Message" : f"Server directory successfully deleted: '{Path}'"
                })
            else:
                self.SFTPObject.remove(Path)       
                self.serverMessage.emit({
                    "Message" : f"Server file successfully deleted: '{Path}'"
                })

    def TransferFilesServerRequest(self):     
        try:
            StartTime = time.time()
            self.TransferFiles(
                self.MiscParameters["Transfer Data"]
                , self.MiscParameters["Local Path"]
                , self.MiscParameters["Server Path"]
                , self.MiscParameters["Transfer Type"]
                , self.MiscParameters["File Extensions"]
            )
            self.completeDataSignal.emit({
                "Local Path" : self.MiscParameters["Local Path"]
                , "Local Results" : self.QueryForADirectoriesContentsLocal(self.MiscParameters["Local Path"], self.MiscParameters["File Extensions"]) 
                , "Server Path" : self.MiscParameters["Server Path"]
                , "Server Results" : self.QueryForADirectoriesContentsRemote(self.MiscParameters["Server Path"], self.MiscParameters["File Extensions"])
                , "Runtime" : round((time.time() - StartTime), 2)
            })        
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    def TransferFiles(self, TransferItems, LocalViewPath, ServerViewPath, TypeOfTransfer, FileExtensions):             
        for Item in TransferItems:
            if not self.CancelSignal:
                #Recursion case. Fetches the next directory's attributes and calls the function again
                if Item["Item Type"] == "Folder":
                    NextFolderLocal = f"{LocalViewPath}/{Item["Item Name"]}"
                    NextFolderServer = f"{ServerViewPath}/{Item["Item Name"]}"
                    if TypeOfTransfer == "Download":
                        QueryResults = self.QueryForADirectoriesContentsRemote(NextFolderServer, FileExtensions)
                        if not os.path.exists(NextFolderLocal):
                            os.mkdir(NextFolderLocal)
                            self.serverMessage.emit({
                                "Message" : f"Local folder sucessfully created at '{NextFolderLocal}'"
                            })
                    elif TypeOfTransfer == "Upload":
                        NextPathItems = os.listdir()
                        QueryResults = self.QueryForADirectoriesContentsLocal(NextFolderLocal, FileExtensions)
                        if not self.ReturnRemoteDirectory(NextFolderServer):
                            self.SFTPObject.mkdir(NextFolderServer)
                            self.serverMessage.emit({
                                "Message" : f"Server folder sucessfully created at '{NextFolderServer}'"
                            })
                    self.TransferFiles(QueryResults, NextFolderLocal, NextFolderServer, TypeOfTransfer, FileExtensions)
                #Base case - Fetches or uploads file in the list
                else:
                    ServerPathItem = f"{ServerViewPath}/{Item["Item Name"]}"
                    LocalPathItem = f"{LocalViewPath}/{Item["Item Name"]}"
                    if TypeOfTransfer == "Download":
                        try:
                            FileStat = self.SFTPObject.stat(ServerPathItem)
                            self.serverMessage.emit({
                                "Message" : f"Starting transfer '{LocalPathItem}' ← '{ServerPathItem}'..."
                                , "Item Size": FileStat.st_size
                            })
                            self.SFTPObject.get(ServerPathItem, LocalPathItem, callback=self.TransferProgess)
                            if LocalViewPath == self.MiscParameters["Local Path"]: #Only update the view for the current path 
                                self.transferCompleteLocal.emit({
                                    "Local Path" : LocalViewPath
                                    , "Directory Items" : self.QueryForADirectoriesContentsLocal(LocalViewPath, FileExtensions)
                                })
                        except FileNotFoundError as FNF: 
                            self.serverMessage.emit({
                                "Message" : f"File not found or symlink broken: '{ServerPathItem}'. Skipping ..."
                            })
                    elif TypeOfTransfer == "Upload": 
                        try:
                            FileSize = os.path.getsize(LocalPathItem)
                            self.serverMessage.emit({
                                "Message" : f"Starting transfer '{LocalPathItem}' → '{ServerPathItem}'..."
                                , "Item Size": FileSize
                            })
                            self.SFTPObject.put(LocalPathItem, ServerPathItem, callback=self.TransferProgess)
                            if ServerViewPath == self.MiscParameters["Server Path"]: 
                                self.transferCompleteRemote.emit({
                                    "Server Path" : ServerViewPath
                                    , "Directory Items" : self.QueryForADirectoriesContentsRemote(ServerViewPath, FileExtensions)
                                })
                        except FileNotFoundError as FNF: 
                            self.serverMessage.emit({
                                "Message" : f"File not found or symlink broken: '{LocalPathItem}'. Skipping ..."
                            })
        
    def TransferProgess(self, bytesSoFar, totalBytes):
        self.transferProgress.emit({
            "Current Bytes": bytesSoFar
            , "Total Bytes": totalBytes
        })

    def ReturnRemoteDirectory(self, ServerPath):
        try:
            DirectoryStats = self.SFTPObject.stat(ServerPath)
            return stat.S_ISDIR(DirectoryStats.st_mode)
        except IOError:
            return False
    
    def ReturnFileExtension(self, FileName, FileExtensions):
        Root, Extension = os.path.splitext(FileName)
        return FileExtensions[Extension] if Extension in FileExtensions else "File"

    def ReturnReadableFileSize(self, Size):
        Units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
        Index = 0
        while Size >= 1024 and Index < len(Units) - 1:
            Size /= 1024
            Index += 1
        return f"{Size:.2f} {Units[Index]}"

    @pyqtSignal(object)
    def CancelCurrentOperation(self):
        self.CancelCalled = True