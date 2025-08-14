from asyncio import create_task, wait, run

from .fe import RelayGuardian
#from .modbus import modbus_operation


def main():
    #from .modbus import ModbusRTUReader

    #app = ModbusReaderApp()
    #root = app.build()
    #app.root = root
    #app.dispatch('on_start')
    #await async_runTouchApp(root)
    #modbus_reader = ModbusRTUReader(cb)

    # while True:
    #     for s in [True, False]:
    #         for i in range(3):
    #             modbus_reader.queue_write_coil(i, s)
    #             await asyncio.sleep(1)

    #modbus_reader.stop()
    RelayGuardian().run()

if __name__ == '__main__':
    from textual.features import parse_features
    import os

    features = set(parse_features(os.environ.get("TEXTUAL", "")))
    features.add("debug")
    features.add("devtools")

    os.environ["TEXTUAL"] = ",".join(sorted(features))

    main()
