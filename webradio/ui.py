from dbus.mainloop.glib import DBusGMainLoop
from webradio.client    import Client
from webradio.config    import Configuration
from webradio.model     import Channel, Station
from webradio.xdg       import get_config_filename

import cairo
import glib
import gtk
import pango

class MarqueLabel(gtk.Widget):
    __gtype_name__ = 'WebRadioMarqueLabel'

    def __init__(self):
        super(MarqueLabel, self).__init__()

        self.__layout = self.create_pango_layout('')
        self.__layout.set_ellipsize(pango.ELLIPSIZE_END)
        self.__xpad, self.__ypad = 9, 3
        self.__gradient = None
        self.__offset = 0

        self.set_flags(gtk.NO_WINDOW)

        def timeout_cb():
            w, h = self.__layout.get_pixel_size()
            self.__offset += 1

            if self.__offset > w:
                self.__offset -= w

            self.queue_draw()
            return True

        glib.timeout_add(60, timeout_cb)

    def do_expose_event(self, event):
        self.style.paint_flat_box(
                event.window, self.state, gtk.SHADOW_NONE, event.area,
                self, None, self.allocation.x, self.allocation.y,
                self.allocation.width, self.allocation.height)

        cr = event.window.cairo_create()
        cr.rectangle(event.area)
        cr.clip()

        fg = self.style.fg[self.state]
        fg = fg.red, fg.green, fg.blue
        r, g, b = [c/65565.0 for c in fg]

        if self.__gradient is None:
            w = self.allocation.width
            p = self.__xpad / float(w)
            q = 1 - p

            self.__gradient = cairo.LinearGradient(0, 0, w, 0)
            self.__gradient.add_color_stop_rgba(0, r, g, b, 0)
            self.__gradient.add_color_stop_rgba(p, r, g, b, 1)
            self.__gradient.add_color_stop_rgba(q, r, g, b, 1)
            self.__gradient.add_color_stop_rgba(1, r, g, b, 0)

        w, h = self.__layout.get_pixel_size()

        cr.set_source(self.__gradient)
        cr.translate(self.allocation.x, self.allocation.y)

        cr.move_to(0 - self.__offset, self.__ypad)
        cr.layout_path(self.__layout)

        cr.move_to(0 - self.__offset + w, self.__ypad)
        cr.layout_path(self.__layout)

        cr.fill()

        return False

    def do_style_set(self, old_style):
        gtk.Widget.do_style_set(self, old_style)
        self.__gradient = None

    def do_size_allocate(self, alloc):
        gtk.Widget.do_size_allocate(self, alloc)
        self.__gradient = None

    def do_size_request(self, req):
        w, h = self.__layout.get_pixel_size()
        req.height = 2 * self.__ypad + h
        req.width = 2 * self.__xpad

    def set_markup(self, markup):
        self.__layout.set_markup(' %s ' % markup)
        self.__offset = 0
        self.queue_resize()


class TagsCompletion(gtk.EntryCompletion):
    __gtype_name__ = 'WebRadioTagsTagsCompletion'

    def __init__(self, tags):
        super(TagsCompletion, self).__init__()

        self.__tags = set(tags)
        model = gtk.ListStore(str)

        for t in tags:
            model.insert(-1, (t, ))

        self.set_model(model)
        self.set_text_column(0)
        self.set_match_func(self.__match_cb)

    def add(self, tags):
        model = self.get_model()

        for t in set(tags).difference(self.__tags):
            model.insert(-1, (t, ))
            self.__tags.add(t)

    def do_match_selected(self, model, iter):
        tag, = model.get(iter, 0)
        entry = self.get_entry()

        try:
            p, s = entry.get_text().rsplit(' ', 1)
            text = p + ' ' + tag + ' '

        except ValueError:
            text = tag + ' '

        entry.set_text (text)
        entry.set_position (-1)

        return True

    @staticmethod
    def __match_cb(completion, key, iter):
        tag, = completion.get_model().get(iter, 0)

        #key = key[:completion.get_entry().get_position()]
        current_tags = key.rsplit(' ')
        key = current_tags[-1]

        if not key:
            return False
        if tag in current_tags:
            return False

        return tag.startswith(key)

class MainWindow(gtk.Window):
    __gtype_name__ = 'WebRadioMainWindow'

    def __init__(self, client=None):
        super(MainWindow, self).__init__()

        if client is None:
            client = Client()

        def channel_compare_cb(model, a, b):
            a, = model.get(a, 0)
            b, = model.get(b, 0)

            return (
                cmp(a.title,         b.title) or
                cmp(a.tags,          b.tags) or
                cmp(a.station.title, b.station.title))

        channels = gtk.ListStore(object)
        channels.set_sort_func(0, channel_compare_cb)
        channels.set_sort_column_id(0, gtk.SORT_ASCENDING)

        tag_completion = TagsCompletion(client.get_tags())
        self.__current_title = None

        def read_wishlist():
            filename = get_config_filename('wishlist')
            wishlist = []

            try:
                text = file(filename).read().strip()
                wishlist = text and text.split('\n') or []

            except IOError:
                pass

            return dict(zip(wishlist, range(len(wishlist))))

        self.__wishlist = read_wishlist()

        def channel_added_cb(client, channel):
            tree_iter = channels.insert(-1, (channel, ))
            tag_completion.add(channel.tags)

            if (channel == client.current_channel or
               (channel.uri == self.__config.channel_uri and
                client.current_channel is None)):

                model = tree_view.get_model()
                tree_iter = model.convert_child_iter_to_iter(tree_iter)
                tree_view.get_selection().select_iter(tree_iter)

        def state_changed_cb(client):
            if client.is_playing:
                self.__config.channel_uri = client.current_channel.uri
                self.__play_button.set_active(True)
                stream_tags_changed_cb(client)

            else:
                self.__pause_button.set_active(True)
                self.__stream_info.hide()

            tree_view.queue_draw()

        def stream_tags_changed_cb(client):
            self.__current_title = client.stream_tags.get('title').strip() or None
            org = client.stream_tags.get('organization').strip() or None
            markup = []

            if self.__current_title:
                markup.append('<b>%s</b>' % glib.markup_escape_text(self.__current_title))
            if org:
                markup.append('<small>%s</small>' % glib.markup_escape_text(org))

            if markup:
                self.__stream_info.set_markup(' - '.join(markup))
                self.__stream_info.set_tooltip_markup('\n'.join(markup))
                self.__stream_info.show()

            else:
                self.__stream_info.set_markup('')
                self.__stream_info.hide()

            self.__favorite_button.set_sensitive(bool(self.__current_title))
            self.__favorite_button.set_active(self.__current_title in self.__wishlist)

        self.__client = client
        self.__client.connect('channel-added',       channel_added_cb)
        self.__client.connect('state-changed',       state_changed_cb)
        self.__client.connect('stream-tags-changed', stream_tags_changed_cb)
        self.__client.wait(Client.STATE_STATIONS_LOADED)

        self.__filter_timeout = 0
        self.__current_tags = []
        self.__config = Configuration()

        def channel_visible_cb(model, iter):
            channel, = model.get(iter, 0)
            return channel.matches(self.__current_tags)

        matching_channels = gtk.TreeModel.filter_new(channels)
        matching_channels.set_visible_func(channel_visible_cb)

        self.set_title('WebRadio')
        self.set_default_size(500, 400)
        self.set_icon_name('rhythmbox')
        self.connect('destroy', gtk.main_quit)

        vbox = gtk.VBox()
        self.add(vbox)

        toolbar = gtk.Toolbar()
        toolbar.set_show_arrow(False)
        vbox.pack_start(toolbar, expand=False)

        def play_button_clicked_cb(button):
            if not button.get_active():
                self.__client.pause()
                return

            model, tree_iter = tree_view.get_selection().get_selected()
            channel = None

            if model and tree_iter:
                channel, = model.get(tree_iter, 0)

            if channel is not None:
                if channel == self.__client.current_channel:
                    self.__client.resume()

                else:
                    self.__client.play(channel)

        def favorite_button_clicked_cb(button):
            if not self.__current_title:
                return

            if button.get_active():
                self.__wishlist[self.__current_title] = True

            else:
                self.__wishlist.pop(self.__current_title, False)

            wishlist_text = '\n'.join(self.__wishlist.keys()) + '\n'
            filename = get_config_filename('wishlist')
            file(filename, 'w').write(wishlist_text)

        self.__play_button = gtk.RadioToolButton(None, gtk.STOCK_MEDIA_PLAY)
        self.__play_button.connect('clicked', play_button_clicked_cb)
        self.__play_button.set_is_important(True)
        toolbar.insert(self.__play_button, -1)

        self.__pause_button = gtk.RadioToolButton(self.__play_button, gtk.STOCK_MEDIA_PAUSE)
        toolbar.insert(self.__pause_button, -1)

        self.__favorite_button = gtk.ToggleToolButton(gtk.STOCK_ABOUT)
        self.__favorite_button.connect('clicked', favorite_button_clicked_cb)
        toolbar.insert(self.__favorite_button, -1)

        item = gtk.SeparatorToolItem()
        item.set_expand(True)
        item.set_draw(False)
        toolbar.insert(item, -1)

        item = gtk.ToolItem()
        toolbar.insert(item, -1)

        def filter_timeout_cb(entry):
            self.__current_tags = filter(None, entry.get_text().split(' '))
            matching_channels.refilter()

            self.__filter_timeout = 0
            return False

        def filter_entry_changed_cb(entry, *args):
            if self.__filter_timeout:
                glib.source_remove(self.__filter_timeout)

            self.__filter_timeout = glib.timeout_add(200, filter_timeout_cb, entry)

        self.__filter_entry = gtk.Entry()
        self.__filter_entry.set_width_chars(40)
        self.__filter_entry.set_completion(tag_completion)
        self.__filter_entry.connect('changed', filter_entry_changed_cb)
        item.add(self.__filter_entry)

        scrolled = gtk.ScrolledWindow()
        scrolled.set_shadow_type(gtk.SHADOW_IN)
        scrolled.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        vbox.pack_start(scrolled, expand=True)

        def row_activated_cb(view, path, column):
            model = view.get_model()
            channel, = model.get(model.get_iter(path), 0)
            self.__client.play(channel)

        tree_view = gtk.TreeView(matching_channels)
        tree_view.set_headers_visible(False)
        tree_view.connect('row-activated', row_activated_cb)
        scrolled.add(tree_view)

        def adjustment_cb(adjustment):
            model, tree_iter = tree_view.get_selection().get_selected()

            if model and tree_iter:
                path = model.get_path(tree_iter)
                tree_view.scroll_to_cell(path, None, True, 0.5, 0.5)

        tree_view.get_vadjustment().connect('changed', adjustment_cb)

        def icon_cell_data_cb(column, cell, model, iter):
            channel, = model.get(iter, 0)

            if channel != self.__client.current_channel:
                cell.set_property('stock-id', None)

            elif self.__client.is_playing:
                cell.set_property('stock-id', gtk.STOCK_MEDIA_PLAY)

            else:
                cell.set_property('stock-id', gtk.STOCK_MEDIA_PAUSE)

        def text_cell_data_cb(column, cell, model, iter):
            channel, = model.get(iter, 0)

            title, tags = channel.title, channel.tags
            tags = [channel.station.id] + list(tags)

            details = title, ' '.join(tags), channel.station.title
            details = tuple(map(glib.markup_escape_text, details))

            markup = '<b>%s</b>\n<small>%s - %s</small>' % details
            cell.set_property('markup', markup)

        cell = gtk.CellRendererPixbuf()
        cell.set_properties(stock_size=gtk.ICON_SIZE_MENU)
        column = gtk.TreeViewColumn('Icon', cell)
        column.set_cell_data_func(cell, icon_cell_data_cb)
        column.set_expand(False)
        tree_view.insert_column(column, -1)

        cell = gtk.CellRendererText()
        cell.set_properties(ellipsize=pango.ELLIPSIZE_END)
        column = gtk.TreeViewColumn(None, cell)
        column.set_cell_data_func(cell, text_cell_data_cb)
        tree_view.insert_column(column, -1)

        self.__stream_info = MarqueLabel()
        self.__stream_info.set_no_show_all(True)
        vbox.pack_start(self.__stream_info, expand=False)

        stream_tags_changed_cb(self.__client)
        state_changed_cb(self.__client)

        tags = (self.__config.tags or '').strip()

        self.__filter_entry.grab_focus()
        self.__filter_entry.set_text(tags + ' ')
        self.__filter_entry.set_position(-1)

        for station in self.__client.get_stations():
            for channel in station.channels:
                channel_added_cb(self.__client, channel)

        self.get_child().show_all()

    def do_destroy(self):
        self.__config.tags = self.__filter_entry.get_text()
        self.__config.write()

    def run(self):
        self.show()
        gtk.main()

if '__main__' == __name__:
    DBusGMainLoop(set_as_default=True)
    MainWindow().run()

