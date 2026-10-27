from importer.settings import load_settings, ConfigError

try:
    print(load_settings())
except ConfigError as e:
    print("CONFIG PROBLEM:", e)
    