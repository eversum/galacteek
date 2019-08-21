from PyQt5.QtWebEngineWidgets import QWebEngineScript
from PyQt5.QtCore import QFile


def scriptFromString(name, jsCode):
    script = QWebEngineScript()
    script.setName(name)
    script.setSourceCode(jsCode)
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    return script


def ipfsClientScripts(connParams):
    scripts = []
    jsFile = QFile(':/share/js/ipfs-http-client/index.min.js')
    if not jsFile.open(QFile.ReadOnly):
        return

    scriptJsIpfs = QWebEngineScript()
    scriptJsIpfs.setName('ipfs-http-client')
    scriptJsIpfs.setSourceCode(jsFile.readAll().data().decode('utf-8'))
    scriptJsIpfs.setWorldId(QWebEngineScript.MainWorld)
    scriptJsIpfs.setInjectionPoint(QWebEngineScript.DocumentCreation)
    scripts.append(scriptJsIpfs)

    script = QWebEngineScript()
    script.setSourceCode('''
        window.ipfs = window.IpfsHttpClient('{host}', '{port}');
    '''.format(
        host=connParams.host,
        port=connParams.apiPort)
    )
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setInjectionPoint(QWebEngineScript.DocumentReady)
    script.setRunsOnSubFrames(True)
    scripts.append(script)
    return scripts


def ethereumClientScripts(connParams):
    scripts = []
    jsFile = QFile(':/share/js/web3.min.js')
    if not jsFile.open(QFile.ReadOnly):
        return None

    scriptWeb3 = QWebEngineScript()
    scriptWeb3.setName('web3.js')
    scriptWeb3.setSourceCode(jsFile.readAll().data().decode('utf-8'))
    scriptWeb3.setWorldId(QWebEngineScript.MainWorld)
    scriptWeb3.setInjectionPoint(QWebEngineScript.DocumentCreation)
    scripts.append(scriptWeb3)

    script = QWebEngineScript()
    if connParams.provType == 'http':
        script.setSourceCode(
            '''
            window.web3 = new Web3(
                new Web3.providers.HttpProvider('{rpcurl}')
            );
            window.web3.eth.defaultAccount = window.web3.eth.accounts[0];
            '''.format(rpcurl=connParams.rpcUrl))
    elif connParams.provType == 'websocket':
        script.setSourceCode(
            '''
            window.web3 = new Web3(
                new Web3.providers.WebsocketProvider('{rpcurl}')
            );
            window.web3.eth.defaultAccount = window.web3.eth.accounts[0];
            '''.format(rpcurl=connParams.rpcUrl))
    else:
        return None

    script.setWorldId(QWebEngineScript.MainWorld)
    script.setName('web3.injector')
    script.setInjectionPoint(QWebEngineScript.DocumentReady)
    script.setRunsOnSubFrames(True)
    scripts.append(script)
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
