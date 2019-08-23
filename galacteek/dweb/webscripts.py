from PyQt5.QtWebEngineWidgets import QWebEngineScript
from PyQt5.QtCore import QFile


def scriptFromString(name, jsCode):
    script = QWebEngineScript()
    script.setName(name)
    script.setSourceCode(jsCode)
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    return script


ipfsInjScript = '''
window.ipfs = window.IpfsHttpClient('{host}', '{port}');
'''


def ipfsClientScripts(connParams):
    scripts = []
    jsFile = QFile(':/share/js/ipfs-http-client/index.min.js')
    if not jsFile.open(QFile.ReadOnly):
        return

    scriptJsIpfs = QWebEngineScript()
    scriptJsIpfs.setName('ipfs-http-client')

    libCode = jsFile.readAll().data().decode('utf-8')
    libCode += "\n"
    libCode += ipfsInjScript.format(
        host=connParams.host,
        port=connParams.apiPort)

    scriptJsIpfs.setSourceCode(libCode)
    scriptJsIpfs.setWorldId(QWebEngineScript.MainWorld)
    scriptJsIpfs.setInjectionPoint(QWebEngineScript.DocumentCreation)
    scriptJsIpfs.setRunsOnSubFrames(True)
    scripts.append(scriptJsIpfs)
    return scripts


w3ScriptHttp = '''
window.web3 = new Web3(
    new Web3.providers.HttpProvider('{rpcurl}')
);
window.web3.eth.defaultAccount = window.web3.eth.accounts[0];
'''

w3ScriptWs = '''
window.web3 = new Web3(
    new Web3.providers.WebsocketProvider('{rpcurl}')
);
window.web3.eth.defaultAccount = window.web3.eth.accounts[0];
'''


def ethereumClientScripts(connParams):
    scripts = []
    jsFile = QFile(':/share/js/web3.min.js')
    if not jsFile.open(QFile.ReadOnly):
        return None

    libCode = jsFile.readAll().data().decode('utf-8')
    libCode += "\n"

    if connParams.provType == 'http':
        libCode += w3ScriptHttp.format(rpcurl=connParams.rpcUrl)
    elif connParams.provType == 'websocket':
        libCode += w3ScriptWs.format(rpcurl=connParams.rpcUrl)

    scriptWeb3 = QWebEngineScript()
    scriptWeb3.setName('web3.js')
    scriptWeb3.setSourceCode(libCode)
    scriptWeb3.setWorldId(QWebEngineScript.MainWorld)
    scriptWeb3.setInjectionPoint(QWebEngineScript.DocumentCreation)
    scripts.append(scriptWeb3)
    return scripts


def orbitScripts(connParams):
    scripts = []
    jsFile = QFile(':/share/js/orbit-db/orbitdb.js')
    if not jsFile.open(QFile.ReadOnly):
        return
    scriptJsIpfs = QWebEngineScript()
    scriptJsIpfs.setName('orbit-db')
    scriptJsIpfs.setSourceCode(jsFile.readAll().data().decode('utf-8'))
    scriptJsIpfs.setWorldId(QWebEngineScript.MainWorld)
    scriptJsIpfs.setInjectionPoint(QWebEngineScript.DocumentCreation)
    scriptJsIpfs.setRunsOnSubFrames(True)
    scripts.append(scriptJsIpfs)

    script = QWebEngineScript()
    script.setSourceCode('\n'.join([
        "document.addEventListener('DOMContentLoaded', function () {",
        "window.orbitdb = new OrbitDB(window.ipfs)",
        "})"]))
    script.setWorldId(QWebEngineScript.MainWorld)
    return scripts
