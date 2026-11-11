from obs.settings import assert_no_demo_users, settings

assert_no_demo_users()

if settings().mode == "demo":
    from obs.demo.ticker import main
else:
    from obs.collector.live import main

main()
