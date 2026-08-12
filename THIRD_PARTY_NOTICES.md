# Third-Party Notices

The bundled DocFerry helper includes the Python interpreter and standard
library under the Python Software Foundation License. See
https://docs.python.org/3/license.html.

The executable is assembled with PyInstaller. PyInstaller is distributed under
GPL-2.0-or-later with a bootloader exception that permits distributing bundled
applications under their own license. See
https://pyinstaller.org/en/stable/license.html.

Development and packaging dependencies are listed in `package-lock.json`. They
are not loaded by the installed extension unless their code is present in the
generated `dist/extension.js` bundle.
