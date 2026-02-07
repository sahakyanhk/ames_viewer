# Makefile for ChimeraX AMES Viewer Bundle

# Detect OS and set ChimeraX executable path
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    # macOS
    CHIMERAX_APP = /Applications/ChimeraX.app
    CHIMERAX_EXE = $(CHIMERAX_APP)/Contents/bin/ChimeraX
else ifeq ($(UNAME_S),Linux)
    # Linux
    CHIMERAX_EXE = chimerax
else
    # Windows (assuming running in a Unix-like shell)
    CHIMERAX_EXE = "C:/Program Files/ChimeraX/bin/ChimeraX-console.exe"
endif

# Allow override via environment variable
ifdef CHIMERAX
    CHIMERAX_EXE = $(CHIMERAX)
endif

.PHONY: all install build clean test

all: install

install:
	$(CHIMERAX_EXE) --nogui --cmd "devel install . ; exit"

build:
	$(CHIMERAX_EXE) --nogui --cmd "devel build . ; exit"

clean:
	$(CHIMERAX_EXE) --nogui --cmd "devel clean . ; exit"
	rm -rf build dist *.egg-info

test:
	$(CHIMERAX_EXE)

uninstall:
	$(CHIMERAX_EXE) --nogui --cmd "toolshed uninstall ChimeraX-AMESViewer ; exit"
