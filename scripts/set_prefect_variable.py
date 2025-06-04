from prefect.variables import Variable

if __name__ == "__main__":
    Variable.set("max_docs_debug", 3, overwrite=True)
    print("Prefect variable 'max_docs_debug' set to 3 (overwrite=True)") 