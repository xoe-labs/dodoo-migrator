# click-odoo-scaffold kick starts your click-odoo project


## To get started

	projectname=migrator
	git clone https://github.com/xoe-labs/click-odoo-scaffold \
	   click-odoo-${projectname} \
	&& cd click-odoo-${projectname} \
	&& make init



## To setup pypi deployment

	make pypi

Note: your password will be obfuscated and uploaded to the travis server.
If `travis` is not installed, the target will automatically install it.


## To pull in updates

	make sync

_Note: Certain files are developped over time in here._
 - `utils` falls under this category,
 - but also common scripts for `testing`.

If you improve one of those files, consisder cherry-picking and propose
here for the greater good.
