"""
src/site - site specific implementations

Description:
    HERALD is designed to accommodate multiple systems in different HPC sites.
    Since every site is different, we embrace this difference instead of trying
    too hard to generalize. The src.site package implements the site specific
    operations required to, for example, access datasets or configurations
    specific to the particular HPC site or system.

    System specific implementations (src/site/<site_name>/<system>/**.py:
        - db.py: database adaptors and views into a particular dataset originated from the system
        - models.py: Definitions and descriptions of the models tied to the system
"""
