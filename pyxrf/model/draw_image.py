# ######################################################################
# Copyright (c) 2014, Brookhaven Science Associates, Brookhaven        #
# National Laboratory. All rights reserved.                            #
#                                                                      #
# Redistribution and use in source and binary forms, with or without   #
# modification, are permitted provided that the following conditions   #
# are met:                                                             #
#                                                                      #
# * Redistributions of source code must retain the above copyright     #
#   notice, this list of conditions and the following disclaimer.      #
#                                                                      #
# * Redistributions in binary form must reproduce the above copyright  #
#   notice this list of conditions and the following disclaimer in     #
#   the documentation and/or other materials provided with the         #
#   distribution.                                                      #
#                                                                      #
# * Neither the name of the Brookhaven Science Associates, Brookhaven  #
#   National Laboratory nor the names of its contributors may be used  #
#   to endorse or promote products derived from this software without  #
#   specific prior written permission.                                 #
#                                                                      #
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS  #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT    #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS    #
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE       #
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,           #
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES   #
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR   #
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)   #
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,  #
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OTHERWISE) ARISING   #
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE   #
# POSSIBILITY OF SUCH DAMAGE.                                          #
########################################################################
from __future__ import absolute_import
__author__ = 'Li Li'

import six
import numpy as np
from collections import OrderedDict
from scipy.interpolate import interp1d, interp2d
import copy

import math
import matplotlib
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import matplotlib.ticker as mticker
import matplotlib.cm as cm
from mpl_toolkits.axes_grid1 import ImageGrid
from atom.api import Atom, Str, observe, Typed, Int, List, Dict, Bool, Float

import logging
logger = logging.getLogger()


def _normalize_data_array(data_in, scaler, *, data_name, name_not_scalable):
    '''
    Normalize data based on the availability of scaler

    Parameters
    ----------

    data_in : ndarray
        numpy array of input data
    scaler : ndarray
        numpy array of scaling data, the same size as data_in
    data_name : str
        name of the data set ('time' or 'i0' etc.)
    name_not_scalable : list
        names of not scalable datasets (['time', 'i0_time'])

    Returns
    -------
    ndarray with normalized data, the same shape as data_in
    '''
    if scaler is not None:
        if data_name in name_not_scalable:
            data_out = data_in
        else:
            data_out = data_in / scaler
    else:
        data_out = data_in

    return data_out

class DrawImageAdvanced(Atom):
    """
    This class performs 2D image rendering, such as showing multiple
    2D fitting or roi images based on user's selection.

    Attributes
    ----------
    img_data : dict
        dict of 2D array
    fig : object
        matplotlib Figure
    file_name : str
    stat_dict : dict
        determine which image to show
    data_dict : dict
        multiple data sets to plot, such as fit data, or roi data
    data_dict_keys : list
    data_opt : int
        index to show which data is chosen to plot
    dict_to_plot : dict
        selected data dict to plot, i.e., fitting data or roi is selected
    items_in_selected_group : list
        keys of dict_to_plot
    scale_opt : str
        linear or log plot
    color_opt : str
        orange or gray plot
    scaler_norm_dict : dict
        scaler normalization data, from data_dict
    scaler_items : list
        keys of scaler_norm_dict
    scaler_name_index : int
        index to select on GUI level
    scaler_data : None or numpy
        selected scaler data
    x_pos : list
        define data range in horizontal direction
    y_pos : list
        define data range in vertical direction
    pixel_or_pos : int
        index to choose plot with pixel (== 0) or with positions (== 1)
    interpolation_opt: bool
        choose to interpolate 2D image in terms of x,y or not
    limit_dict : Dict
        save low and high limit for image scaling
    """

    fig = Typed(Figure)
    stat_dict = Dict()
    data_dict = Dict()
    data_dict_keys = List()
    data_opt = Int(0)
    dict_to_plot = Dict()
    items_in_selected_group = List()
    items_previous_selected = List()

    scale_opt = Str('Linear')
    color_opt = Str('viridis')
    img_title = Str()

    scaler_norm_dict = Dict()
    scaler_items = List()
    scaler_name_index = Int()
    scaler_data = Typed(object)

    x_pos = List()
    y_pos = List()

    pixel_or_pos = Int(0)
    interpolation_opt = Bool(True)
    data_dict_default = Dict()
    limit_dict = Dict()
    range_dict = Dict()
    scatter_show = Bool(False)
    name_not_scalable = List()

    def __init__(self):
        self.fig = plt.figure(figsize=(3,2))
        matplotlib.rcParams['axes.formatter.useoffset'] = True
        self.name_not_scalable = ['r2_adjust','alive', 'dead', 'elapsed_time', 'scaler_alive', 
                                  'i0_time', 'time', 'time_diff'] # do not apply scaler norm on those data

    def data_dict_update(self, change):
        """
        Observer function to be connected to the fileio model
        in the top-level gui.py startup

        Parameters
        ----------
        changed : dict
            This is the dictionary that gets passed to a function
            with the @observe decorator
        """
        self.data_dict = change['value']

    def set_default_dict(self, data_dict):
        self.data_dict_default = copy.deepcopy(data_dict)

    @observe('data_dict')
    def init_plot_status(self, change):
        scaler_groups = [v for v in list(self.data_dict.keys()) if 'scaler' in v]
        if len(scaler_groups) > 0:
            #self.scaler_group_name = scaler_groups[0]
            self.scaler_norm_dict = self.data_dict[scaler_groups[0]]
            # for GUI purpose only
            self.scaler_items = []
            self.scaler_items = list(self.scaler_norm_dict.keys())
            self.scaler_items.sort()
            self.scaler_data = None

        # init of pos values
        self.pixel_or_pos = 0

        if 'positions' in self.data_dict:
            try:
                logger.info('get pos {}'.format(list(self.data_dict['positions'].keys())))
                self.x_pos = list(self.data_dict['positions']['x_pos'][0, :])
                self.y_pos = list(self.data_dict['positions']['y_pos'][:, -1])
                # when we use imshow, the x and y start at lower left,
                # so flip y, we want y starts from top left
                self.y_pos.reverse()

            except KeyError:
                pass
        else:
            self.x_pos = []
            self.y_pos = []

        self.get_default_items()   # use previous defined elements as default
        logger.info('Use previously selected items as default: {}'.format(self.items_previous_selected))

        # initiate the plotting status once new data is coming
        self.reset_to_default()
        self.data_dict_keys = []
        self.data_dict_keys = list(self.data_dict.keys())
        logger.debug('The following groups are included for 2D image display: {}'.format(self.data_dict_keys))

        self.show_image()

    def reset_to_default(self):
        """Set variables to default values as initiated.
        """
        self.data_opt = 0
        # init of scaler for normalization
        self.scaler_name_index = 0
        self.plot_deselect_all()

    def get_default_items(self):
        """Add previous selected items as default.
        """
        if len(self.items_previous_selected) != 0:
            default_items = {}
            for item in self.items_previous_selected:
                for v, k in self.data_dict.items():
                    if item in k:
                        default_items[item] = k[item]
            self.data_dict['use_default_selection'] = default_items

    @observe('data_opt')
    def _update_file(self, change):
        try:
            if self.data_opt == 0:
                self.dict_to_plot = {}
                self.items_in_selected_group = []
                self.set_stat_for_all(bool_val=False)
                self.img_title = ''
            elif self.data_opt > 0:
                #self.set_stat_for_all(bool_val=False)
                plot_item = sorted(self.data_dict_keys)[self.data_opt-1]
                self.img_title = str(plot_item)
                self.dict_to_plot = self.data_dict[plot_item]
                self.set_stat_for_all(bool_val=False)

                self.update_img_wizard_items()
                self.get_default_items()   # get default elements every time when fitting is done

        except IndexError:
            pass

    @observe('scaler_name_index')
    def _get_scaler_data(self, change):
        if change['type'] == 'create':
            return

        if self.scaler_name_index == 0:
            self.scaler_data = None
        else:
            try:
                scaler_name = self.scaler_items[self.scaler_name_index-1]
            except IndexError:
                scaler_name = None
            if scaler_name:
                self.scaler_data = self.scaler_norm_dict[scaler_name]
                logger.info('Use scaler data to normalize, '
                            'and the shape of scaler data is {}, '
		            'with (low, high) as ({}, {})'.format(self.scaler_data.shape,
		    	    				          np.min(self.scaler_data),
							          np.max(self.scaler_data)))
        self.set_low_high_value() # reset low high values based on normalization
        self.show_image()
        self.update_img_wizard_items()

    def update_img_wizard_items(self):
        """This is for GUI purpose only.
        Table items will not be updated if list items keep the same.
        """
        self.items_in_selected_group = []
        self.items_in_selected_group = list(self.dict_to_plot.keys())

    def format_img_wizard_limit(self, value):
        """
        This function is used for formatting of range values in 'Image Wizard'.
        The presentation of the number was tweaked so that it is nicely formatted
           in the enaml field with adequate precision.

        ..note::
        
        The function is called externally from 'enaml' code.

        Parameters:
        ===========
        value : float
            The value to be formatted

        Returns:
        ========
        str - the string representation of the floating point variable
        """
        if value != 0:
            value_log10 = math.log10(abs(value))
        else:
            value_log10 = 0
        if (value_log10 > 3) or (value_log10 < -3):
            return f"{value:.6e}"
        return f"{value:.6f}"

    @observe('scale_opt', 'color_opt')
    def _update_scale(self, change):
        if change['type'] != 'create':
            self.show_image()

    @observe('pixel_or_pos')
    def _update_pp(self, change):
            self.show_image()

    def plot_select_all(self):
        self.set_stat_for_all(bool_val=True)

    def plot_deselect_all(self):
        self.set_stat_for_all(bool_val=False)

    @observe('scatter_show')
    def _change_image_plot_method(self, change):
        if change['type'] != 'create':
            self.show_image()

    def set_stat_for_all(self, bool_val=False):
        """
        Set plotting status for all the 2D images, including low and high values.
        """
        self.stat_dict.clear()
        self.stat_dict = {k: bool_val for k in self.dict_to_plot.keys()}

        self.limit_dict.clear()
        self.limit_dict = {k: {'low':0.0, 'high': 100.0} for k in self.dict_to_plot.keys()}

        self.set_low_high_value()

    def set_low_high_value(self):
        """Set default low and high values based on normalization for each image.
        """
        # do not apply scaler norm on not scalable data
        self.range_dict.clear()
        for data_name in self.dict_to_plot.keys():
            data_arr = _normalize_data_array(self.dict_to_plot[data_name], self.scaler_data,
                                             data_name=data_name, name_not_scalable=self.name_not_scalable)
            lowv = np.min(data_arr)
            highv = np.max(data_arr)
            self.range_dict[data_name] = {'low': lowv, 'low_default': lowv,
                                          'high': highv, 'high_default': highv}

    def reset_low_high(self, name):
        """Reset low and high value to default based on normalization.
        """
        self.range_dict[name]['low'] = self.range_dict[name]['low_default']
        self.range_dict[name]['high'] = self.range_dict[name]['high_default']
        self.limit_dict[name]['low'] = 0.0
        self.limit_dict[name]['high'] = 100.0
        self.update_img_wizard_items()
        self.show_image()

    def show_image(self):
        self.fig.clf()
        stat_temp = self.get_activated_num()
        stat_temp = OrderedDict(sorted(six.iteritems(stat_temp), key=lambda x: x[0]))

        low_lim = 1e-4  # define the low limit for log image
        plot_interp = 'Nearest'

        if self.scaler_data is not None:
            if len(self.scaler_data[self.scaler_data == 0]) > 0:
                logger.warning('scaler data has zero values at {}'.format(np.where(self.scaler_data == 0)))
                self.scaler_data[self.scaler_data == 0] = np.mean(self.scaler_data[self.scaler_data > 0])
                logger.warning('Use mean value {} instead for those points'.format(np.mean(self.scaler_data[self.scaler_data > 0])))

        grey_use = self.color_opt

        ncol = int(np.ceil(np.sqrt(len(stat_temp))))
        try:
            nrow = int(np.ceil(len(stat_temp)/float(ncol)))
        except ZeroDivisionError:
            ncol = 1
            nrow = 1

        a_pad_v = 0.8
        a_pad_h = 0.5

        grid = ImageGrid(self.fig, 111,
                         nrows_ncols=(nrow, ncol),
                         axes_pad=(a_pad_v, a_pad_h),
                         cbar_location='right',
                         cbar_mode='each',
                         cbar_size='7%',
                         cbar_pad='2%',
                         share_all=True)


        def _compute_equal_axes_ranges(x_min, x_max, y_min, y_max):
            """
            Compute ranges for x- and y- axes of the plot. Make sure that the ranges for x- and y-axes are
            always equal and fit the maximum of the ranges for x and y values:
                  max(abs(x_max-x_min), abs(y_max-y_min))
            The ranges are set so that the data is always centered in the middle of the ranges

            Parameters
            ----------

            x_min, x_max, y_min, y_max : float
                lower and upper boundaries of the x and y values

            Returns
            -------

            x_axis_min, x_axis_max, y_axis_min, y_axis_max : float
                lower and upper boundaries of the x- and y-axes ranges
            """

            x_axis_min, x_axis_max, y_axis_min, y_axis_max = x_min, x_max, y_min, y_max
            x_range, y_range = abs(x_max - x_min), abs(y_max - y_min)
            if x_range > y_range:
                y_center = (y_max + y_min) / 2
                y_axis_max = y_center + x_range / 2
                y_axis_min = y_center - x_range / 2
            else:
                x_center = (x_max + x_min) / 2
                x_axis_max = x_center + y_range / 2
                x_axis_min = x_center - y_range / 2

            return x_axis_min, x_axis_max, y_axis_min, y_axis_max

        def _adjust_data_range__min_ratio(c_min, c_max, c_axis_range, *, min_ratio=0.01):
            """
            Adjust the range for plotted data along one axis (x or y). The adjusted range is
            applied to the 'extend' attribute of imshow(). The adjusted range is always greater
            than 'axis_range * min_ratio'. Such transformation has no physical meaning
            and performed for aesthetic reasons: stretching the image presentation of
            a scan with only a few lines (1-3) greatly improves visibility of data.

            Parameters
            ----------

            c_min, c_max : float
                boundaries of the data range (along x or y axis)
            c_axis_range : float
                range presented along the same axis

            Returns
            -------

            cmin, c_max : float
                adjusted boundaries of the data range
            """
            c_range = c_max - c_min
            if c_range < c_axis_range * min_ratio:
                c_center = (c_max + c_min) / 2
                c_new_range = c_axis_range * min_ratio
                c_min = c_center - c_new_range / 2
                c_max = c_center + c_new_range / 2
            return c_min, c_max

        for i, (k, v) in enumerate(six.iteritems(stat_temp)):

            data_dict = _normalize_data_array(data_in=self.dict_to_plot[k],
                                              scaler=self.scaler_data,
                                              data_name=k,
                                              name_not_scalable=self.name_not_scalable)

            if self.pixel_or_pos or self.scatter_show:

                #xd_min, xd_max, yd_min, yd_max = min(self.x_pos), max(self.x_pos), min(self.y_pos), max(self.y_pos)
                x_pos_2D = self.data_dict['positions']['x_pos']
                y_pos_2D = self.data_dict['positions']['y_pos']
                xd_min, xd_max, yd_min, yd_max = x_pos_2D.min(), x_pos_2D.max(), y_pos_2D.min(), y_pos_2D.max()
                xd_axis_min, xd_axis_max, yd_axis_min, yd_axis_max = _compute_equal_axes_ranges(xd_min, xd_max, yd_min, yd_max)

                xd_min, xd_max = _adjust_data_range__min_ratio(xd_min, xd_max, xd_axis_max - xd_axis_min)
                yd_min, yd_max = _adjust_data_range__min_ratio(yd_min, yd_max, yd_axis_max - yd_axis_min)

                # Adjust the direction of each axis depending on the direction in which encoder values changed
                #   during the experiment. Data is plotted starting from the upper-right corner of the plot
                if x_pos_2D[0, 0] > x_pos_2D[0, -1]:
                    xd_min, xd_max, xd_axis_min, xd_axis_max = xd_max, xd_min, xd_axis_max, xd_axis_min
                if y_pos_2D[0, 0] > y_pos_2D[-1, 0]:
                    yd_min, yd_max, yd_axis_min, yd_axis_max = yd_max, yd_min, yd_axis_max, yd_axis_min

            else:

                yd, xd = data_dict.shape

                xd_min, xd_max, yd_min, yd_max = 0, xd, 0, yd
                if (yd <= 5) and (xd >= 200):
                    yd_min, yd_max = -5, 4
                if (xd <= 5) and (yd >= 200):
                    xd_min, xd_max = -5, 4

                xd_axis_min, xd_axis_max, yd_axis_min, yd_axis_max = _compute_equal_axes_ranges(xd_min, xd_max, yd_min, yd_max)

            if self.scale_opt == 'Linear':

                low_ratio = self.limit_dict[k]['low']/100.0
                high_ratio = self.limit_dict[k]['high']/100.0
                if self.scaler_data is None:
                    minv = self.range_dict[k]['low']
                    maxv = self.range_dict[k]['high']
                else:
                    # Unfortunately, the new normalization procedure requires to recalculate min and max values
                    minv = np.min(data_dict)
                    maxv = np.max(data_dict)
                low_limit = (maxv-minv)*low_ratio + minv
                high_limit = (maxv-minv)*high_ratio + minv

                # Set some minimum range for the colorbar (otherwise it will have white fill)
                if math.isclose(low_limit, high_limit, abs_tol=2e-20):
                    if abs(low_limit) < 1e-20:  # The value is zero
                        dv = 1e-20
                    else:
                        dv = low_limit * 0.01
                    high_limit += dv
                    low_limit -= dv

                if self.scatter_show is not True:
                    im = grid[i].imshow(data_dict,
                                        cmap=grey_use,
                                        interpolation=plot_interp,
                                        extent=(xd_min, xd_max, yd_max, yd_min),
                                        origin='upper',
                                        clim=(low_limit, high_limit))
                    grid[i].set_ylim(yd_axis_max, yd_axis_min)
                else:
                    # Colorbar range can not be easily controlled in 'scatter' plot
                    # To control the range, amend the plotted data so that
                    #   1. all the data points fall within the desired range
                    #   2. the data points include values at the edges of the range
                    #        (the range is defined with 'high_limit' and 'low_limit')
                    #   Note: 'high_limit' must not necessarily be larger than 'low_limit'
                    # To satisfy the requirement #2 we add two extra points to the plotted
                    #   dataset. Those points should not be visible, so they are placed
                    #   outside the visible plot region.
                    xx = self.data_dict['positions']['x_pos'].flatten()
                    yy = self.data_dict['positions']['y_pos'].flatten()
                    data_dict = np.clip(data_dict, low_limit, high_limit)
                    x_jump = 2 * xd_axis_max - xd_axis_min
                    y_jump = 2 * yd_axis_max - yd_axis_min
                    xx = np.append(xx, [x_jump, x_jump])
                    yy = np.append(yy, [y_jump, y_jump])
                    data_dict = np.append(data_dict, [high_limit, low_limit])
                    im = grid[i].scatter(xx, yy, c=data_dict,
                                         marker='s', s=500,
                                         alpha=1.0,  # Originally: alpha=0.8
                                         cmap=grey_use,
                                         linewidths=1, linewidth=0)
                    grid[i].set_ylim(yd_axis_max, yd_axis_min)

                grid[i].set_xlim(xd_axis_min, xd_axis_max)

                grid_title = k
                grid[i].text(0, 1.01, grid_title, ha='left', va='bottom', transform=grid[i].axes.transAxes)

                grid.cbar_axes[i].colorbar(im)
                im.colorbar.formatter = im.colorbar.cbar_axis.get_major_formatter()
                #im.colorbar.ax.get_xaxis().set_ticks([])
                #im.colorbar.ax.get_xaxis().set_ticks([], minor=True)
                grid.cbar_axes[i].ticklabel_format(style='sci', scilimits=(-3,4), axis='both')
                
                # Do not remove this code, may be useful in the future (Dmitri G.) !!!
                # Print label for colorbar 
                #cax = grid.cbar_axes[i]
                #axis = cax.axis[cax.orientation]
                #axis.label.set_text("$[a.u.]$")

                grid[i].get_xaxis().get_major_formatter().set_useOffset(False)
                grid[i].get_yaxis().get_major_formatter().set_useOffset(False)

            else:

                maxz = np.max(data_dict)
                # Set some reasonable minimum range for the colorbar
                #   Zeros or negative numbers will be shown in white
                if maxz <= 1e-30:
                    maxz = 1

                if self.scatter_show is not True:
                    im = grid[i].imshow(data_dict,
                                        norm=LogNorm(vmin=low_lim*maxz,
                                                    vmax=maxz, clip=True),
                                        cmap=grey_use,
                                        interpolation=plot_interp,
                                        extent=(xd_min, xd_max, yd_max, yd_min),
                                        origin='upper',
                                        clim=(low_lim*maxz, maxz))
                    grid[i].set_ylim(yd_axis_max, yd_axis_min)
                else:
                    im = grid[i].scatter(self.data_dict['positions']['x_pos'],
                                         self.data_dict['positions']['y_pos'],
                                         norm=LogNorm(vmin=low_lim*maxz,
                                                      vmax=maxz, clip=True),
                                         c=data_dict, marker='s', s=500, alpha=1.0,  # Originally: alpha=0.8
                                         cmap=grey_use,
                                         linewidths=1, linewidth=0)
                    grid[i].set_ylim(yd_axis_min, yd_axis_max)

                grid[i].set_xlim(xd_axis_min, xd_axis_max)

                grid_title = k
                grid[i].text(0, 1.01, grid_title, ha='left', va='bottom', transform=grid[i].axes.transAxes)

                grid.cbar_axes[i].colorbar(im)
                im.colorbar.formatter = im.colorbar.cbar_axis.get_major_formatter()
                im.colorbar.ax.get_xaxis().set_ticks([])
                im.colorbar.ax.get_xaxis().set_ticks([], minor=True)
                im.colorbar.cbar_axis.set_minor_formatter(mticker.LogFormatter())

                grid[i].get_xaxis().get_major_formatter().set_useOffset(False)
                grid[i].get_yaxis().get_major_formatter().set_useOffset(False)

        self.fig.suptitle(self.img_title, fontsize=20)
        self.fig.canvas.draw_idle()


    def get_activated_num(self):
        """Collect the selected items for plotting.
        """
        current_items = {k: v for (k, v) in six.iteritems(self.stat_dict) if v is True}
        return current_items

    def record_selected(self):
        """Save the list of items in cache for later use.
        """
        self.items_previous_selected = [k for (k,v) in self.stat_dict.items() if v is True]
        logger.info('Items are set as default: {}'.format(self.items_previous_selected))
        self.data_dict['use_default_selection'] = {k:self.dict_to_plot[k] for k in self.items_previous_selected}
        self.data_dict_keys = list(self.data_dict.keys())
