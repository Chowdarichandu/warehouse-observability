from obs.settings import settings

if settings().mode == "demo":
    from obs.demo.ticker import main
else:
    from obs.collector.live import main

main()
