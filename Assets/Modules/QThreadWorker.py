from PyQt6.QtCore import pyqtSignal, pyqtSlot, QObject
import datetime, stat, os, time, math

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
        self.CancelSignal = False

    #Opens SSH/SFTP connection and emits for the default ssh directory path for application use
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

    #Safely disconnects an SSH/SFTP connection, if ones exists
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

    #Request handler for getting the required local directory information
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

    #Function to return the local directory information for a given local file path. Requires file extension information for reference
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

    #Request handler for getting the required remote directory information
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

    #Function to return the remote directory information for a given remote file path. Requires file extension information for reference
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
            
    #Request handler for renaming a remote file. Returns the remote directory information to update the application
    def RenameFileOrDirectory(self):
        try:
            if self.MiscParameters["Old Name"] != self.MiscParameters["New Name"]:
                self.SFTPObject.rename(
                    self.MiscParameters["Old Name"]
                    , self.MiscParameters["New Name"]
                )
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

    #Request handler for deleting remote files. Returns the remote directory information to update the application
    def DeleteFileOrDirectoryServerRequest(self):
        try:
            StartTime = time.time()
            self.DeleteFilesOrDirectories(
                self.MiscParameters["Directory Items"]
                , self.MiscParameters["Server Path"]
            )
            QueryResults = self.QueryForADirectoriesContentsRemote(self.MiscParameters["Server Path"], self.MiscParameters["File Extensions"])
            if (type(QueryResults) == list):
                self.completeDataSignal.emit({
                    "Server Path" : self.MiscParameters["Server Path"]
                    , "Server Results" : QueryResults
                })
            else:
                raise QueryResults
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    #Recursive function to delete a list of given items and their sub directory contents, if any
    def DeleteFilesOrDirectories(self, ItemsToDelete, ItemPath):
        for Item in ItemsToDelete:
            CurrentItemPath = os.path.join(ItemPath, Item["Item Name"])
            if "Folder" in Item["Item Type"] and self.ReturnRemoteDirectory(CurrentItemPath):
                self.DeleteFilesOrDirectories(
                    self.QueryForADirectoriesContentsRemote(CurrentItemPath, self.MiscParameters["File Extensions"])
                    , CurrentItemPath
                ) 
                self.SFTPObject.rmdir(CurrentItemPath)
                self.serverMessage.emit({
                    "Message" : f"Server directory successfully deleted: '{CurrentItemPath}'"
                })
            else:
                self.SFTPObject.remove(CurrentItemPath)
                self.serverMessage.emit({
                    "Message" : f"Server file successfully deleted: '{CurrentItemPath}'"
                })

    #Request handler for transfering files between a remote and local machine
    def TransferFilesServerRequest(self):     
        try:
            StartTime = time.time()
            self.TransferFiles(
                self.MiscParameters["Transfer Data"]
                , self.MiscParameters["Local Path"]
                , self.MiscParameters["Server Path"]
            )
            self.completeDataSignal.emit({
                "Local Path" : self.MiscParameters["Local Path"]
                , "Local Results" : self.QueryForADirectoriesContentsLocal(self.MiscParameters["Local Path"], self.MiscParameters["File Extensions"]) 
                , "Server Path" : self.MiscParameters["Server Path"]
                , "Server Results" : self.QueryForADirectoriesContentsRemote(self.MiscParameters["Server Path"], self.MiscParameters["File Extensions"])
                , "Runtime" : math.ceil((time.time() - StartTime) * (10 ** 2)) / (10 ** 2)
            })        
        except Exception as e: 
            self.completeDataSignal.emit({
                "Error Thrown" : e
            })

    #Recursive function that takes a given list of directory items from either the local or remote machines, a local path, and a remote path and moves the files appropriately
    def TransferFiles(self, TransferItems, LocalViewPath, ServerViewPath):             
        for Item in TransferItems:
            if not self.CancelSignal:
                NextItemLocal = os.path.join(LocalViewPath, Item["Item Name"])
                NextItemServer = os.path.join(ServerViewPath, Item["Item Name"]) 
                if "Folder" in Item["Item Type"]: 
                    if self.MiscParameters["Transfer Type"] == "Download":
                        if not os.path.exists(NextItemLocal):
                            os.mkdir(NextItemLocal)
                            self.serverMessage.emit({
                                "Message" : f"Local folder sucessfully created at '{NextItemLocal}'"
                            })
                        QueryResults = self.QueryForADirectoriesContentsRemote(NextItemServer, self.MiscParameters["File Extensions"])
                    elif self.MiscParameters["Transfer Type"] == "Upload":
                        if not self.ReturnRemoteDirectory(NextItemServer):
                            self.SFTPObject.mkdir(NextItemServer)
                            self.serverMessage.emit({
                                "Message" : f"Server folder sucessfully created at '{NextItemServer}'"
                            })
                        QueryResults = self.QueryForADirectoriesContentsLocal(NextItemLocal, self.MiscParameters["File Extensions"])
                    self.TransferFiles(QueryResults, NextItemLocal, NextItemServer)
                else:  
                    if self.MiscParameters["Transfer Type"] == "Download":
                        try:
                            FileStat = self.SFTPObject.stat(NextItemServer)
                            self.serverMessage.emit({
                                "Message" : f"Starting transfer '{NextItemLocal}' ← '{NextItemServer}'..."
                                , "Item Size": FileStat.st_size
                            })
                            self.SFTPObject.get(NextItemServer, NextItemLocal, callback=self.TransferProgess)
                            if LocalViewPath == self.MiscParameters["Local Path"]: #Only update the view for the current path 
                                self.transferCompleteLocal.emit({
                                    "Local Path" : LocalViewPath
                                    , "Directory Items" : self.QueryForADirectoriesContentsLocal(LocalViewPath, self.MiscParameters["File Extensions"])
                                })
                        except FileNotFoundError as FNF: 
                            self.serverMessage.emit({
                                "Message" : f"File not found or symlink broken: '{NextItemServer}'. Skipping ..."
                            })
                    elif self.MiscParameters["Transfer Type"] == "Upload": 
                        try:
                            FileSize = os.path.getsize(NextItemLocal)
                            self.serverMessage.emit({
                                "Message" : f"Starting transfer '{NextItemLocal}' → '{NextItemServer}'..."
                                , "Item Size": FileSize
                            })
                            self.SFTPObject.put(NextItemLocal, NextItemServer, callback=self.TransferProgess)
                            if ServerViewPath == self.MiscParameters["Server Path"]: 
                                self.transferCompleteRemote.emit({
                                    "Server Path" : ServerViewPath
                                    , "Directory Items" : self.QueryForADirectoriesContentsRemote(ServerViewPath, self.MiscParameters["File Extensions"])
                                })
                        except FileNotFoundError as FNF: 
                            self.serverMessage.emit({
                                "Message" : f"File not found or symlink broken: '{NextItemLocal}'. Skipping ..."
                            })
        
    #Callback function to update the application with transfer progress information
    def TransferProgess(self, bytesSoFar, totalBytes):
        self.transferProgress.emit({
            "Current Bytes": bytesSoFar
            , "Total Bytes": totalBytes
        })

    #Function to return whether a path is a server path or a local path
    def ReturnRemoteDirectory(self, ServerPath):
        try:
            DirectoryStats = self.SFTPObject.stat(ServerPath)
            return stat.S_ISDIR(DirectoryStats.st_mode)
        except IOError:
            return False
    
    #Function that returns a readable string about the file type
    def ReturnFileExtension(self, FileName, FileExtensions):
        Root, Extension = os.path.splitext(FileName)
        return FileExtensions[Extension] if Extension in FileExtensions else "File"

    #Function that returns a readable file size type given a parameter of byte count
    def ReturnReadableFileSize(self, Size):
        Units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
        Index = 0
        while Size >= 1024 and Index < len(Units) - 1:
            Size /= 1024
            Index += 1
        return f"{Size:.2f} {Units[Index]}"

    #Signal function to set the cancel signal of a transfer
    @pyqtSlot()
    def CancelCurrentOperation(self):
        self.CancelSignal = True
        print("Test")
        self.serverMessage.emit({
            "Message" : f"Made it to the server message function"
        })
