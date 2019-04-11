def migrate(cr, version):
    cr.execute("""INSERT INTO dodoo_test_migrations VALUES ('end')""")
