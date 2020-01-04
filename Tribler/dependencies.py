"""
This file lists the python dependencies for Tribler.

Note that this file should not depend on any external modules itself other than builtin ones.
"""
import importlib
import sys

dependencies = [
    {'module': 'PyQt5', 'install_type': 'pip3', 'package': 'PyQt5', 'optional': False, 'scope': 'gui'},
    {'module': 'twisted', 'install_type': 'pip3', 'package': 'Twisted', 'optional': False, 'scope': 'core'},
    {'module': 'libtorrent', 'install_type': 'apt', 'package': 'python-libtorrent', 'optional': False,
     'scope': 'core'},
    {'module': 'cryptography', 'install_type': 'pip3', 'package': 'cryptograpy>=2.3', 'optional': False,
     'scope': 'core'},
    {'module': 'libnacl', 'install_type': 'pip3', 'package': 'libnacl', 'optional': False, 'scope': 'core'},
    {'module': 'pony', 'install_type': 'pip3', 'package': 'pony>=0.7.10', 'optional': False, 'scope': 'core'},
    {'module': 'lz4', 'install_type': 'pip3', 'package': 'lz4', 'optional': False, 'scope': 'core'},
    {'module': 'psutil', 'install_type': 'pip3', 'package': 'psutil', 'optional': False, 'scope': 'both'},
    {'module': 'networkx', 'install_type': 'pip3', 'package': 'networkx', 'optional': False, 'scope': 'both'},
    {'module': 'pyqtgraph', 'install_type': 'pip3', 'package': 'pyqtgraph', 'optional': False, 'scope': 'gui'},
    {'module': 'chardet', 'install_type': 'pip3', 'package': 'chardet', 'optional': False, 'scope': 'core'},
    {'module': 'cherrypy', 'install_type': 'pip3', 'package': 'cherrypy', 'optional': False, 'scope': 'core'},
    {'module': 'configobj', 'install_type': 'pip3', 'package': 'configobj', 'optional': False, 'scope': 'both'},
    {'module': 'netifaces', 'install_type': 'pip3', 'package': 'netifaces', 'optional': False, 'scope': 'core'},
    {'module': 'six', 'install_type': 'pip3', 'package': 'six', 'optional': False, 'scope': 'both'},
    {'module': 'bitcoinlib', 'install_type': 'pip3', 'package': 'bitcoinlib', 'optional': True, 'scope': 'core'},
    {'module': 'PIL', 'install_type': 'pip3', 'package': 'PIL', 'optional': False, 'scope': 'gui'},
    {'module': 'pyasn1', 'install_type': 'pip3', 'package': 'pyasn1', 'optional': False, 'scope': 'core'},
]


def _show_system_popup(title, text):
    """
    Create a native pop-up without any third party dependency.

    :param title: the pop-up title
    :param text: the pop-up body
    """
    try:
        import win32api
        win32api.MessageBox(0, text, title)
    except ImportError:
        import subprocess
        subprocess.Popen(['xmessage', '-center', text])
    sep = "*" * 80
    print('\n'.join([sep, title, sep, text, sep]), file=sys.stderr)


def check_for_missing_dependencies(scope='both'):
    """
    Checks modules installed with pip, especially via linux post installation script.
    Program exits with a dialog if there are any missing dependencies.

    :param scope: Defines the scope of the dependencies. Can have three values: core, gui, both. Default value is both.
    """
    missing_deps = {'pip3': [], 'apt': []}
    is_scope_both = scope == 'both'
    for dep in dependencies:
        if not is_scope_both and dep['scope'] != 'both' and dep['scope'] != scope:
            continue
        try:
            importlib.import_module(dep['module'])
        except ImportError:
            if not dep['optional']:
                if dep['install_type'] == 'pip3':
                    missing_deps['pip3'].append(dep['package'])
                elif dep['install_type'] == 'apt':
                    missing_deps['apt'].append(dep['package'])

    if missing_deps['pip3'] or missing_deps['apt']:
        pip3_install = f"\n pip3 install {' '.join(missing_deps['pip3'])}" if missing_deps['pip3'] else ''
        apt_install = f"\n apt install {' '.join(missing_deps['apt'])}" if missing_deps['apt'] else ''
        _show_system_popup("Dependencies missing!",
                           f"Tribler -  found missing dependencies in {scope}!\n"
                           "Please install the following dependencies to continue:"
                           f"\n {pip3_install}{apt_install} \n\n"
                           )
        exit(1)
