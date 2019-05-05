def migrate(cr, version):
    query = """
    CREATE TABLE IF NOT EXISTS dodoo_test_migrations (
        name VARCHAR NOT NULL
    );
    """
    cr.execute(query)

    cr.execute("""INSERT INTO dodoo_test_migrations VALUES ('pre')""")
