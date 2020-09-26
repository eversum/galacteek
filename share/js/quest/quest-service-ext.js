
async function start() {
    window.qosService = new window.GalacteekQuestService();

    let config = {
        ipfs: {                                                                                
            bootstrap: [
                "@@WS_BOOTSTRAP_ADDR@@"
            ],
            api: '/ip4/127.0.0.1/tcp/4004'
        },
        version: 1.0,
        dev: false
    };

    window.qosService.setConfig(config)

    window.qosService.os.onReady().subscribe(async(r) => {
        console.log('qOS ready')

        window.qosService.os.onSignIn().subscribe(async(r) => {
            console.log('Signed in')

            chan = await window.qosService.os.channel.create('galacteek')
            console.log(chan)

            await window.qosService.os.channel.publish(chan, 'Test message')
        })

        window.qosService.os.signIn({})
    })

    await window.qosService.boot()
}

setTimeout(async() => { await start() }, 1200)
