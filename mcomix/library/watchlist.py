""" Library watch list dialog and backend classes. """

import os
import gtk
import gobject

from mcomix.library import backend_types
from mcomix.preferences import prefs


COL_DIRECTORY = 0
COL_COLLECTION = 0
COL_COLLECTION_ID = 1
COL_RECURSIVE = 2

class WatchListDialog(gtk.Dialog):
    """ Dialog for managing watched directories. """

    RESPONSE_SCANNOW = 1000

    def __init__(self, library):
        """ Dialog constructor.
        @param library: Dialog parent window, should be library window.
        """
        super(WatchListDialog, self).__init__(_("Library watch list"),
            library, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL,
            (_('_Scan now').encode('utf-8'), WatchListDialog.RESPONSE_SCANNOW,
             gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))

        #: Stores a reference to the library
        self.library = library
        #: True if changes were made to the watchlist. Not 100% accurate.
        self._changed = False

        self.set_default_response(gtk.RESPONSE_CLOSE)

        # Initialize treeview control showing existing watch directories
        self._treeview = gtk.TreeView(self._create_model())
        self._treeview.set_headers_visible(True)
        self._treeview.get_selection().connect('changed', self._item_selected_cb)

        dir_renderer = gtk.CellRendererText()
        dir_column = gtk.TreeViewColumn(_("Directory"), dir_renderer)
        dir_column.set_attributes(dir_renderer, text=COL_DIRECTORY)
        dir_column.set_expand(True)
        self._treeview.append_column(dir_column)

        collection_model = self._create_collection_model()
        collection_renderer = gtk.CellRendererCombo()
        collection_renderer.set_property('model', collection_model)
        collection_renderer.set_property('text-column', COL_COLLECTION)
        collection_renderer.set_property('editable', gtk.TRUE)
        collection_renderer.set_property('has-entry', gtk.FALSE)
        collection_renderer.connect('changed', self._collection_changed_cb, collection_model)
        collection_column = gtk.TreeViewColumn(_("Collection"), collection_renderer)
        collection_column.set_cell_data_func(collection_renderer,
                self._treeview_collection_id_to_name)
        self._treeview.append_column(collection_column)

        recursive_renderer = gtk.CellRendererToggle()
        recursive_renderer.set_activatable(True)
        recursive_renderer.connect('toggled', self._recursive_changed_cb)
        recursive_column = gtk.TreeViewColumn(_("With subdirectories"),
                recursive_renderer)
        recursive_column.add_attribute(recursive_renderer, 'active', COL_RECURSIVE)
        self._treeview.append_column(recursive_column)

        add_button = gtk.Button(_("_Add"), gtk.STOCK_ADD)
        add_button.connect('clicked', self._add_cb)
        self._remove_button = remove_button = gtk.Button(_("_Remove"), gtk.STOCK_REMOVE)
        remove_button.set_sensitive(False)
        remove_button.connect('clicked', self._remove_cb)

        button_box = gtk.VBox()
        button_box.pack_start(add_button, expand=False)
        button_box.pack_start(remove_button, expand=False, padding=2)

        main_box = gtk.HBox()
        scroll_window = gtk.ScrolledWindow()
        scroll_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll_window.add(self._treeview)
        main_box.pack_start(scroll_window, padding=2)
        main_box.pack_end(button_box, expand=False)
        self.vbox.pack_start(main_box)

        auto_checkbox = gtk.CheckButton(
            _('Automatically scan for new books when library is _opened'), True)
        auto_checkbox.set_active(prefs['scan for new books on library startup'])
        auto_checkbox.connect('toggled', self._auto_scan_toggled_cb)
        self.vbox.pack_end(auto_checkbox, False, False, 5)

        self.resize(475, 350)
        self.connect('response', self._close_cb)
        self.show_all()

    def get_selected_watchlist_entry(self):
        """ Returns the selected watchlist entry, or C{None} if no
        item is selected. """
        selection = self._treeview.get_selection()

        model, iter = selection.get_selected()
        if iter is not None:
            path = unicode(model.get_value(iter, COL_DIRECTORY))
            return self.library.backend.watchlist.get_watchlist_entry(path)
        else:
            return None

    def get_watchlist_entry_for_treepath(self, treepath):
        """ Converts a tree path to WatchlistEntry object. """
        model = self._treeview.get_model()
        iter = model.get_iter(treepath)
        dirpath = unicode(model.get_value(iter, COL_DIRECTORY))
        return self.library.backend.watchlist.get_watchlist_entry(dirpath)

    def _create_model(self):
        """ Creates a model containing all watched directories. """
        # Watched directory, associated library collection ID
        model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_INT, gobject.TYPE_BOOLEAN)
        self._fill_model(model)
        return model

    def _fill_model(self, model):
        """ Empties the model's data and updates it from the database. """
        model.clear()
        for entry in self.library.backend.watchlist.get_watchlist():
            if entry.collection.id is None:
                id = -1
            else:
                id = entry.collection.id

            model.append((entry.directory, id, entry.recursive))

    def _create_collection_model(self):
        """ Creates a model containing all available collections. """
        # Collection ID, collection name
        model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_INT)

        ids = self.library.backend.get_all_collections()
        model.append((backend_types.DefaultCollection.name, -1))
        for id in ids:
            model.append((self.library.backend.get_collection_name(id), id))

        return model

    def _collection_changed_cb(self, column, path,
                               collection_iter, collection_model, *args):
        """ A new collection was set for a watched directory. """
        # Get new collection ID from collection model
        new_id = collection_model.get_value(collection_iter, COL_COLLECTION_ID)
        collection = self.library.backend.get_collection_by_id(new_id)

        # Update database
        self.get_watchlist_entry_for_treepath(path).set_collection(collection)

        # Update collection ID in watchlist model
        model = self._treeview.get_model()
        iter = model.get_iter(path)
        # Editing the model in the CellRendererCombo callback stops the editing
        # operation, causing GTK warnings. Delay until callback is finished.
        gobject.idle_add(model.set_value, iter, COL_COLLECTION_ID, new_id)

        self._changed = True

    def _recursive_changed_cb(self, toggle_renderer, path, *args):
        """ Recursive reading was enabled or disabled. """
        status = not toggle_renderer.get_active()
        self.get_watchlist_entry_for_treepath(path).set_recursive(status)

        # Update recursive status in watchlist model
        model = self._treeview.get_model()
        iter = model.get_iter(path)
        model.set_value(iter, COL_RECURSIVE, status)

        self._changed = True

    def _add_cb(self, button, *args):
        """ Called when a new watch list entry should be added. """
        filechooser = gtk.FileChooserDialog(parent=self,
            action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                     gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        result = filechooser.run()
        if filechooser.get_filename() is not None:
            directory = filechooser.get_filename().decode('utf-8')
        else:
            directory = u""
        filechooser.destroy()

        if result == gtk.RESPONSE_ACCEPT \
            and os.path.isdir(directory):

            self.library.backend.watchlist.add_directory(directory)
            self._fill_model(self._treeview.get_model())

            self._changed = True

    def _remove_cb(self, button, *args):
        """ Called when a watch list entry should be removed. """
        entry = self.get_selected_watchlist_entry()
        if entry:
            entry.remove()

            # Remove selection from list
            selection = self._treeview.get_selection()
            model, iter = selection.get_selected()
            model.remove(iter)

    def _item_selected_cb(self, selection, *args):
        """ Called when an item is selected. Enables or disables the "Remove"
        button. """
        self._remove_button.set_sensitive(selection.count_selected_rows() > 0)

    def _auto_scan_toggled_cb(self, checkbox, *args):
        """ Toggles automatic library book scanning. """
        prefs['scan for new books on library startup'] = checkbox.get_active()

    def _treeview_collection_id_to_name(self, column, cell, model, iter, *args):
        """ Maps a collection ID to the corresponding collection name. """
        id = model.get_value(iter, COL_COLLECTION_ID)
        if id != -1:
            text = self.library.backend.get_collection_name(id)
        else:
            text = backend_types.DefaultCollection.name

        cell.set_property("text", text)

    def _close_cb(self, dialog, response, *args):
        """ Trigger scan for new files after watch dialog closes. """
        self.destroy()
        if response == gtk.RESPONSE_CLOSE and self._changed:
            self.library.scan_for_new_files()
        elif response == WatchListDialog.RESPONSE_SCANNOW:
            self.library.scan_for_new_files()


# vim: expandtab:sw=4:ts=4
