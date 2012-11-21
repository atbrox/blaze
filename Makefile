.PHONY: docs tests build clean web

build:
	python setup.py build_ext --inplace

docs:
	cd docs; make html

images:
	cd docs/source/svg; make

web:
	cd web; make html

cleandocs:
	cd docs; make clean

tests:
	nosetests -s -v --detailed
	#nosetests --rednose -s -v ndtable


clean:
	python setup.py clean
