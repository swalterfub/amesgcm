#!/usr/bin/env python3

#Load generic Python Modules
import argparse #parse arguments
import os       #access operating systems function
import subprocess #run command
import sys       #system command


#==============
from amesgcm.Script_utils import check_file_tape,prYellow,prRed,prCyan,prGreen,prPurple
from amesgcm.Script_utils import print_fileContent,print_varContent,FV3_file_type,find_tod_in_diurn
from amesgcm.Script_utils import wbr_cmap,rjw_cmap,dkass_temp_cmap,dkass_dust_cmap
from amesgcm.FV3_utils import lon360_to_180,lon180_to_360,UT_LTtxt,area_weights_deg
from amesgcm.FV3_utils import add_cyclic,azimuth2cart,mollweide2cart,robin2cart,ortho2cart
#=====Attempt to import specific scientic modules one may not find in the default python on NAS ====
try:
    import matplotlib
    matplotlib.use('Agg') # Force matplotlib to not use any Xwindows backend.
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import MultipleLocator, FuncFormatter  #format ticks
    from netCDF4 import Dataset, MFDataset
    from numpy import sqrt, exp, max, mean, min, log, log10,sin,cos,abs
    from matplotlib.colors import LogNorm
    from matplotlib.ticker import LogFormatter

except ImportError as error_msg:
    prYellow("Error while importing modules")
    prYellow('Your are using python '+str(sys.version_info[0:3]))
    prYellow('Please, source your virtual environment');prCyan('    source envPython3.7/bin/activate.csh \n')
    print("Error was: ", error_msg)
    exit()
except Exception as exception:
    # Output unexpected Exceptions.
    print(exception.__class__.__name__ + ": ", exception)
    exit()


#======================================================
#                  ARGUMENTS PARSER
#======================================================

global current_version;current_version=3.2
parser = argparse.ArgumentParser(description="""\033[93mAnalysis Toolkit for the Ames GCM, V%s\033[00m """%(current_version),
                                formatter_class=argparse.RawTextHelpFormatter)

parser.add_argument('custom_file', nargs='?',type=argparse.FileType('r'),default=None, #sys.stdin
                             help='Use optional input file Custom.in to plot the graphs \n'
                                  '> Usage: MarsPlot Custom.in  [other options]\n'
                                  'UPDATE as needed with \033[96mpip3 install git+https://github.com/alex-kling/amesgcm.git --upgrade\033[00m \n'
                                  'Tutorial at: \033[93mhttps://github.com/alex-kling/amesgcm\033[00m')

parser.add_argument('-i', '--inspect_file', default=None,
                 help="""Inspect Netcdf file content. Variables are sorted by dimensions \n"""
                      """> Usage: MarsPlot -i 00000.atmos_daily.nc\n"""
                      """Options: use --dump (variable content) and --stat (min, mean,max) jointly with --inspect \n"""
                      """>  MarsPlot -i 00000.atmos_daily.nc -dump pfull 'temp[6,:,30,10]'  (quotes '' are needed when browsing dimensions)\n"""
                      """>  MarsPlot -i 00000.atmos_daily.nc -stat 'ucomp[5,:,:,:]' 'vcomp[5,:,:,:]'\n""")
#These two options are to be used jointly with --inspect
parser.add_argument('--dump','-dump', nargs='+',default=None,
                    help=argparse.SUPPRESS)
parser.add_argument('--stat','-stat', nargs='+',default=None,
                    help=argparse.SUPPRESS)

help=argparse.SUPPRESS
parser.add_argument('-d','--date', nargs='+',default=None,
                 help='Specify the range of files to use, default is the last file  \n'
                      '> Usage: MarsPlot Custom.in -d 700     (one file) \n'
                      '         MarsPlot Custom.in -d 350 700 (start file end file)')

parser.add_argument('--template','-template', action='store_true',
                        help="""Generate a template Custom.in for customization of the plots.\n """
                             """(Use '--temp' for a skinned version of the template)\n""")
parser.add_argument('-temp','--temp', action='store_true',help=argparse.SUPPRESS) #same as --template but without the instructions

parser.add_argument('-do','--do', nargs=1,type=str,default=None, #sys.stdin
                             help='(Re)-use a template file my_custom.in. First search in ~/amesGCM3/mars_templates/,\n'
                                 '                                                then in /u/mkahre/MCMC/analysis/working/shared_templates/ \n'
                                  '> Usage: MarsPlot -do my_custom [other options]')

parser.add_argument('-sy', '--stack_year', action='store_true',default=False,
                 help='Stack consecutive years in 1D time series instead of having them back to back\n'
                     '> Usage: MarsPlot Custom.in -sy \n')

parser.add_argument("-o", "--output",default="pdf",
                 choices=['pdf','eps','png'],
                 help='Output file format\n'
                       'Default is pdf if ghostscript (gs) is available and png otherwise\n'
                        '> Usage: MarsPlot Custom.in -o png \n'
                        '       : MarsPlot Custom.in -o png -pw 500 (set pixel width to 500, default is 2000)\n')

parser.add_argument('-vert', '--vertical', action='store_true',default=False,
                 help='Output figures as vertical pages instead of horizonal \n')


parser.add_argument("-pw", "--pwidth",default=2000,type=float,
                 help=argparse.SUPPRESS)


parser.add_argument('-dir', '--directory', default=os.getcwd(),
                 help='Target directory if input files are not present in current directory \n'
                      '> Usage: MarsPlot Custom.in [other options] -dir /u/akling/FV3/verona/c192L28_dliftA/history')


parser.add_argument('--debug',  action='store_true', help='Debug flag: do not by-pass errors on a particular figure')
#======================================================
#                  MAIN PROGRAM
#======================================================
def main():

    global output_path ; output_path = os.getcwd()
    global input_paths  ; input_paths=[];input_paths.append(parser.parse_args().directory)
    global out_format  ; out_format=parser.parse_args().output
    global debug       ;debug =parser.parse_args().debug
    global Ncdf_num         #host the simulation timestamps
    global objectList      #contains all figure object
    global customFileIN    #template name
    global levels;levels=21 #number of contour for 2D plots
    global my_dpi;my_dpi=96.        #pixel per inch for figure output
    global label_size;label_size=12 #Label size for title, xlabel, ylabel
    global label_factor;label_factor=1/2# reduce the font size as the  number of pannel increases size
    global width_inch; #pixel width for saving figure
    global height_inch; #pixel width for saving figure
    global vertical_page;vertical_page=parser.parse_args().vertical #vertical pages instead of horizonal for saving figure
    global shared_dir; shared_dir='/u/mkahre/MCMC/analysis/working/shared_templates' #directory containing shared templates

    #Set Figure dimensions
    pixel_width=parser.parse_args().pwidth
    if vertical_page:
        width_inch=pixel_width/1.4/my_dpi;height_inch=pixel_width/my_dpi
    else:
        width_inch=pixel_width/my_dpi;height_inch=pixel_width/1.4/my_dpi


    objectList=[Fig_2D_lon_lat('fixed.zsurf',True),\
                Fig_2D_lat_lev('atmos_average.ucomp',True),\
                Fig_2D_time_lat('atmos_average.taudust_IR',False),\
                Fig_2D_lon_lev('atmos_average_pstd.temp',False),\
                Fig_2D_time_lev('atmos_average_pstd.temp',False),\
                Fig_2D_lon_time('atmos_average.temp',False),\
                Fig_1D('atmos_average.temp',False)]
        #=============================
    #----------Group together the 1st two figures----
    objectList[0].subID=1;objectList[0].nPan=2 #1st object of a 2 panel figure
    objectList[1].subID=2;objectList[1].nPan=2 #2nd object of a 2 panel figure

    # Begin main loop:


    # ----- Option 1 :Inspect content of a Netcdf file ----
    if parser.parse_args().inspect_file:
        check_file_tape(parser.parse_args().inspect_file,abort=False) #NAS-specific, check if the file is on tape

        if parser.parse_args().dump:
            #Dumping variable content
            print_varContent(parser.parse_args().inspect_file,parser.parse_args().dump,False)
        elif parser.parse_args().stat:
            #Printing variable stats
            print_varContent(parser.parse_args().inspect_file,parser.parse_args().stat,True)
        else:
            # Show information on all the variables
            print_fileContent(parser.parse_args().inspect_file)


        # ----- Option 2: Generate a template file ----
    elif parser.parse_args().template or parser.parse_args().temp:
        make_template()

    # --- Gather simulation information from template or inline argument
    else:

        # --- Option 2, case A:   Use Custom.in  for everything ----
        if parser.parse_args().custom_file:
           print('Reading '+parser.parse_args().custom_file.name)
           namelist_parser(parser.parse_args().custom_file.name)


        # --- Option 2, case B:   Use Custom.in in ~/FV3/templates for everything ----
        if parser.parse_args().do:
           print('Reading '+path_to_template(parser.parse_args().do))
           namelist_parser(path_to_template(parser.parse_args().do))


        # Set bounds  (e.g. starting file, end file)
        if parser.parse_args().date: #a date single date or a range is provided
            # first check if the value provided is the right type
            try:
                bound=np.asarray(parser.parse_args().date).astype(np.float)
            except Exception as e:
                prRed('*** Syntax Error***')
                prRed("""Please use:   'MarsPlot Custom.in -d XXXX [YYYY] -o out' """)
                exit()

        else: # no date is provided, default is last file XXXXX.fixed.nc in directory
            bound=get_Ncdf_num()
            #If one or multiple  XXXXX.fixed.nc files are found, use the last one
            if bound is not None :bound=bound[-1]
        #-----

        #Initialization
        Ncdf_num=get_Ncdf_num() #Get all timestamps in directory

        if Ncdf_num  is not None:
            Ncdf_num=select_range(Ncdf_num,bound)  # Apply bounds to the desired dates
            nfiles=len(Ncdf_num)                   #number of timestamps
        else: #No XXXXX.fixed.nc, in the directory. It is assumed we will be looking at one single file
            nfiles=1


        #print('MarsPlot is running...')
        #Make a ./plots folder in the current directory if it does not exist
        dir_plot_present=os.path.exists(output_path+'/'+'plots')
        if not dir_plot_present:
            os.makedirs(output_path+'/'+'plots')

        fig_list=list()#list of figures

        #============Do plots==================
        global i_list;
        for i_list in range(0,len(objectList)):

            status=objectList[i_list].plot_type+' :'+objectList[i_list].varfull
            progress(i_list,len(objectList),status,None) #display the figure in progress

            objectList[i_list].do_plot()

            if objectList[i_list].success and out_format=='pdf' and not debug : sys.stdout.write("\033[F");sys.stdout.write("\033[K") #if success,flush the previous output

            status=objectList[i_list].plot_type+' :'+objectList[i_list].varfull+objectList[i_list].fdim_txt
            progress(i_list,len(objectList),status,objectList[i_list].success)
            # Add the figure to the list of figures
            if objectList[i_list].subID==objectList[i_list].nPan: #only for the last panel of a subplot
                if i_list< len(objectList)-1 and not objectList[i_list+1].addLine:
                    fig_list.append(objectList[i_list].fig_name)
                #Last subplot
                if i_list== len(objectList)-1 :fig_list.append(objectList[i_list].fig_name)

        progress(100,100,'Done')# 100% completed


        #========Making multipage pdf=============
        if out_format=="pdf" and len(fig_list)>0:
            print('Merging figures...')
            #print("Plotting figures:",fig_list)
            debug_filename=output_path+'/.debug_MCMC_plots.txt' #debug file (masked), use to redirect the outputs from ghost script
            fdump = open(debug_filename, 'w') #
            #Construct list of figures----

            all_fig=' '
            for figID in fig_list:
                #Add outer quotes(" ") to deal with white space in Windows, e.g. '"/Users/my folder/Diagnostics.pdf"'
                figID='"'+figID+'"'
                all_fig+=figID+' '

            #Output name for the pdf
            try:
                if parser.parse_args().do:
                    basename=parser.parse_args().do[0]
                else:
                    input_file=output_path+'/'+parser.parse_args().custom_file.name
                    basename=input_file.split('/')[-1].split('.')[0].strip() #get the input file name, e.g "Custom_01" or

            except: #Special case where no Custom.in is provided
                basename='Custom'


            #default name is Custom.in, output Diagnostics.pdf
            if basename=='Custom':
                output_pdf=fig_name=output_path+'/'+'Diagnostics.pdf'
            #default name is Custom_XX.in, output Diagnostics_XX.pdf
            elif  basename[0:7]=="Custom_":
                output_pdf=fig_name=output_path+'/Diagnostics_'+basename[7:9]+'.pdf' #same name as input file
            #name is different use it
            else:
                output_pdf=fig_name=output_path+'/'+basename+'.pdf' #same name as input file

            #Also add outer quote to the output pdf
            output_pdf='"'+output_pdf+'"'
            #command to make a multipage pdf out of the the individual figures using ghost scritp.
            # Also remove the temporary files when done
            cmd_txt='gs -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -dEPSCrop -sOutputFile='+output_pdf+' '+all_fig
            #=======ON NAS, the ghostscript executable has been renamed 'gs.bin'. If the above fail, we will also try this one========
            try:
                subprocess.check_call(cmd_txt,shell=True, stdout=fdump, stderr=fdump)
            except subprocess.CalledProcessError:
                cmd_txt='gs.bin -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -dEPSCrop -sOutputFile='+output_pdf+' '+all_fig
            #================
            try:
                #Test the ghost script and remove command, exit otherwise--
                subprocess.check_call(cmd_txt,shell=True, stdout=fdump, stderr=fdump)
                #Execute the commands now
                subprocess.call(cmd_txt,shell=True, stdout=fdump, stderr=fdump) #run ghostscript to merge the pdf
                cmd_txt='rm -f '+all_fig
                subprocess.call(cmd_txt,shell=True, stdout=fdump, stderr=fdump)#remove temporary pdf figs
                cmd_txt='rm -f '+'"'+debug_filename+'"'
                subprocess.call(cmd_txt,shell=True)#remove debug file
                #If the plot directory was not present initially, remove it
                if not dir_plot_present:
                    cmd_txt='rm -r '+'"'+output_path+'"'+'/plots'
                    subprocess.call(cmd_txt,shell=True)
                give_permission(output_pdf)
                print(output_pdf + ' was generated')

            except subprocess.CalledProcessError:
                print("ERROR with ghostscript when merging pdf, please try alternative formats")
                if debug:raise



#======================================================
#                  DATA OPERATION UTILITIES
#======================================================

def shift_data(lon,data):
    '''
    This function shift the longitude and data from a 0->360 to a -180/+180 grid.
    Args:
        lon: 1D array of longitude 0->360
        data: 2D array with last dimension being the longitude
    Returns:
        lon: 1D array of longitude -180/+180
        data: shifted data
    Note: Use np.ma.hstack instead of np.hstack to keep the masked array properties
    '''
    lon_180=lon.copy()
    nlon=len(lon_180)
    # for 1D plots: if 1D, reshape array
    if len(data.shape) <=1:
        data=data.reshape(1,nlon)
    #===
    lon_180[lon_180>180]-=360.
    data=np.hstack((data[:,lon_180<0],data[:,lon_180>=0]))
    lon_180=np.append(lon_180[lon_180<0],lon_180[lon_180>=0])
    # If 1D plot, squeeze array
    if data.shape[0]==1:
        data=np.squeeze(data)
    return lon_180,data


def MY_func(Ls_cont):
    '''
    This function return the Mars Year
    Args:
        Ls_cont: solar longitude, contineuous
    Returns:
        MY : int the Mars year
    '''
    return (Ls_cont)//(360.)+1



def get_lon_index(lon_query_180,lons):
    '''
    Given a range of requested longitudes, return the indexes to extract data from the netcdf file
    Args:
        lon_query_180: requested longitudes in -180/+180 units: value, [min, max] or None
        lons:          1D array of longitude in the native coordinates (0->360)
    Returns:
        loni: 1D array of file indexes
        txt_lon: text descriptor for the extracted longitudes
    *** Note that the keyword 'all' is passed as -99999 by the rT() functions
    '''
    Nlon=len(lons)
    lon_query_180=np.array(lon_query_180)

    #If None, set to default, i.e 'all' for a zonal average
    if lon_query_180.any()==None: lon_query_180=np.array(-99999)

    #=============FV3 format ==============
    # lons are 0>360, convert to -180>+180
    #======================================
    if lons.max()>180:
        #one longitude is provided
        if lon_query_180.size==1:
            #request zonal average
            if lon_query_180==-99999:
                loni=np.arange(0,Nlon)
                txt_lon=', zonal avg'
            else:
                #get closet value
                lon_query_360=lon180_to_360(lon_query_180)
                loni=np.argmin(np.abs(lon_query_360-lons))
                txt_lon=', lon=%.1f'%(lon360_to_180(lons[loni]))
        # a range is requested
        elif lon_query_180.size==2:
            lon_query_360=lon180_to_360(lon_query_180)
            loni_bounds=np.array([np.argmin(np.abs(lon_query_360[0]-lons)),np.argmin(np.abs(lon_query_360[1]-lons))])
            #if loni_bounds[0]>loni_bounds[1]:loni_bounds=np.flipud(loni_bounds) #lon should be increasing for extraction #TODO
            #Normal case, e.g. -45W>45E
            if loni_bounds[0]<loni_bounds[1]:
                loni=np.arange(loni_bounds[0],loni_bounds[1]+1)
            else:
                #Loop around, e.g, 160E>-40W
                loni=np.append(np.arange(loni_bounds[0],len(lons)),np.arange(0,loni_bounds[1]+1))
                prPurple(lon360_to_180(lons[loni]))
            lon_bounds_180=lon360_to_180([lons[loni_bounds[0]],lons[loni_bounds[1]]])

            #if lon_bounds_180[0]>lon_bounds_180[1]:lon_bounds_180=np.flipud(lon_bounds_180) #lon should be also increasing for display
            txt_lon=', lon=avg[%.1f<->%.1f]'%(lon_bounds_180[0],lon_bounds_180[1])

        #=========Legacy  format ===========
        # lons are already -180>+180
        #===================================
    else:
        #one longitude is provided
        if lon_query_180.size==1:
            #request zonal average
            if lon_query_180==-99999:
                loni=np.arange(0,Nlon)
                txt_lon=', zonal avg'
            else:
                #get closet value
                loni=np.argmin(np.abs(lon_query_180-lons))
                txt_lon=', lon=%.1f'%(lons[loni])
        # a range is requested
        elif lon_query_180.size==2:
            loni_bounds=np.array([np.argmin(np.abs(lon_query_180[0]-lons)),np.argmin(np.abs(lon_query_180[1]-lons))])
            #Normal case, e.g. -45W>45E
            if loni_bounds[0]<loni_bounds[1]:
                loni=np.arange(loni_bounds[0],loni_bounds[1]+1)
            else:
                #Loop around, e.g, 160E>-40W
                loni=np.append(np.arange(loni_bounds[0],len(lons)),np.arange(0,loni_bounds[1]+1))
            txt_lon=', lon=avg[%.1f<->%.1f]'%(lons[loni_bounds[0]],lons[loni_bounds[1]])

    return loni,txt_lon

def get_lat_index(lat_query,lats):
    '''
    Given a range of requested latitudes, return the indexes to extract data from the netcdf file
    Args:
        lat_query: requested latitudes -90/+90
        lats:      1D array of latitudes in the native coordinates
    Returns:
        lati: 1D array of file indexes
        txt_lat: text descriptor for the extracted latitudes
    *** Note that the keyword 'all' is passed as -99999 by the rT() functions
    '''
    Nlat=len(lats)
    lat_query=np.array(lat_query)
    #If None, set to default, i.e equator
    if lat_query.any()==None: lat_query=np.array(0.)
    #one latitude is provided
    if lat_query.size==1:
        #request meridional average
        if lat_query==-99999:
            lati=np.arange(0,Nlat)
            txt_lat=', merid. avg'
        else:
            #get closet value
            lati=np.argmin(np.abs(lat_query-lats))
            txt_lat=', lat=%g'%(lats[lati])
    # a range is requested
    elif lat_query.size==2:
        lat_bounds=np.array([np.argmin(np.abs(lat_query[0]-lats)),np.argmin(np.abs(lat_query[1]-lats))])
        if lat_bounds[0]>lat_bounds[1]:lat_bounds=np.flipud(lat_bounds) #lat should be incresing for extraction
        lati=np.arange(lat_bounds[0],lat_bounds[1]+1)
        txt_lat=', lat=avg[%g<->%g]'%(lats[lati[0]],lats[lati[-1]])
    return lati,txt_lat

def get_tod_index(tod_query,tods):
    '''
    Given a range of requested time of day, return the indexes to extract data from the netcdf file
    Args:
        tod_query: requested time of day, 0-24
        tods:      1D array of time of days in the native coordinates
    Returns:
        todi: 1D array of file indexes
        txt_tod: text descriptor for the extracted time of day
    *** Note that the keyword 'all' is passed as -99999 by the rT() functions
    '''
    Ntod=len(tods)
    tod_query=np.array(tod_query)
    #If None, set to default, i.e 3pm
    if tod_query.any()==None: tod_query=np.array(15)
    #one latitude is provided
    if tod_query.size==1:
        #request meridional average
        if tod_query==-99999:
            todi=np.arange(0,Ntod)
            txt_tod=', tod avg'
        else:
            #get closet value
            todi=np.argmin(np.abs(tod_query-tods))
            txt_tmp=UT_LTtxt(tods[todi]/24.,lon_180=0.,roundmin=1)
            txt_tod=', tod= %s'%(txt_tmp)
    # a range is requested
    elif tod_query.size==2:
        tod_bounds=np.array([np.argmin(np.abs(tod_query[0]-tods)),np.argmin(np.abs(tod_query[1]-tods))])
        #Normal case, e.g. 4am>10am
        if tod_bounds[0]<tod_bounds[1]:
            todi=np.arange(tod_bounds[0],tod_bounds[1]+1)
        else:
            #Loop around, e.g, 18pm>6am
            todi=np.append(np.arange(tod_bounds[0],len(tods)),np.arange(0,tod_bounds[1]+1))
        txt_tmp=UT_LTtxt(tods[todi[0]]/24.,lon_180=0.,roundmin=1)
        txt_tmp2=UT_LTtxt(tods[todi[-1]]/24.,lon_180=0.,roundmin=1)
        txt_tod=', tod=avg[%s<->%s]'%(txt_tmp,txt_tmp2)
    return todi,txt_tod


def get_level_index(level_query,levs):
    '''
    Given a range of requested pressures (resp. depth for 'zgrid'), return the indexes to extract data from the netcdf file
    Args:
        level_query: requested  pressure in [Pa] (resp. depth in [m])
        levs:         1D array of levels in the native coordinates [Pa] (resp. [m])
    Returns:
        levi: 1D array of file indexes
        txt_lev: text descriptor for the extracted pressure (resp. depth)
    *** Note that the keyword 'all' is passed as -99999 by the rT() functions
    '''
    level_query=np.array(level_query)
    Nz=len(levs)
    #If None, set to default, i.e  surface
    if level_query.any()== None: level_query=np.array(2*10**7) #a big number > Psfc (even for a 10bar Early Mars simulation)

    #one level is provided
    if level_query.size==1:
        #average
        if level_query==-99999:
            levi=np.arange(0,Nz)
            txt_level=', column avg'
        #specific level
        else:
            levi=np.argmin(np.abs(level_query-levs))

        # provide smart labelling
            if level_query>10.**7: #None, i.e sfc was requested
                txt_level=', at sfc'
            else:
                #txt_level=', lev=%g Pa'%(levs[levi])
                txt_level=', lev={0:1.2e} Pa/m'.format(levs[levi])

    elif level_query.size==2: #bounds are provided
        levi_bounds=np.array([np.argmin(np.abs(level_query[0]-levs)),np.argmin(np.abs(level_query[1]-levs))])
        if levi_bounds[0]>levi_bounds[1]:levi_bounds=np.flipud(levi_bounds) #level should be incresing for extraction
        levi=np.arange(levi_bounds[0],levi_bounds[1]+1)
        lev_bounds=[levs[levi[0]],levs[levi[-1]]] #this is for display
        if lev_bounds[0]<lev_bounds[1]:lev_bounds=np.flipud(lev_bounds) #lev should be also decreasing for display
        txt_level=', lev=avg[{0:1.2e}<->{1:1.2e}] Pa/m'.format(lev_bounds[0],lev_bounds[1])

    return levi,txt_level

def get_time_index(Ls_query_360,Ls):
    '''
    Given a range of requested solar longitude [0-360], return the indexes to extract data from the netcdf file.
    First try the Mars year of the last timestep, then try the year before then picks whichever Ls period is closest to the requested date.

    Args:
        Ls_query_360: requested  solar longitudes
        Ls_c:         1D array of continueous solar longitudes
    Returns:
        ti: 1D array of file indexes
        txt_time: text descriptor for the extracted solar longitudes
    *** Note that the keyword 'all' is passed as -99999 by the rT() functions
    '''

    #Special case where the file has only one timestep, transform Ls to array:
    if len(np.atleast_1d(Ls))==1:Ls=np.array([Ls])

    Nt=len(Ls)
    Ls_query_360=np.array(Ls_query_360)

    #If None, set to default, i.e last time step
    if Ls_query_360.any()==None: Ls_query_360=np.mod(Ls[-1],360.)

    #one time is provided
    if Ls_query_360.size==1:
        #time average average requested
        if Ls_query_360==-99999:
            ti=np.arange(0,Nt)
            txt_time=', time avg'
        else:
            #get the Mars year of the last timestep in the file
            MY_end=MY_func(Ls[-1]) #number of Mars year at the end of the file.
            if MY_end >=1:
            #check if the desired Ls is available for this Mars Year
                Ls_query=Ls_query_360+(MY_end-1)*360. #(MY starts at 1, not zero)
            else:
                Ls_query=Ls_query_360
            #If this time is greater that the last Ls, look one year back
            if Ls_query>Ls[-1] and MY_end>1:
                MY_end-=1 #one year back
                Ls_query=Ls_query_360+(MY_end-1)*360.
            ti=np.argmin(np.abs(Ls_query-Ls))
            txt_time=', Ls= (MY%2i) %.2f'%(MY_end,np.mod(Ls[ti],360.))

    # a range is requested
    elif Ls_query_360.size==2:

        #get the Mars year of the last timestep in the file
        MY_last=MY_func(Ls[-1]) #number of Mars year at the end of the file.
        if MY_last >=1:
        #try the mars year of the last time step
            Ls_query_last=Ls_query_360[1]+(MY_last-1)*360.
        else:
            Ls_query_last=Ls_query_360[1]
        #First consider the further end of the desired range
        #This time is greater that the last Ls, look one year back
        if Ls_query_last>Ls[-1] and  MY_last>1:
            MY_last-=1
            Ls_query_last=Ls_query_360[1]+(MY_last-1)*360. #(MY starts at 1, not zero)
        ti_last=np.argmin(np.abs(Ls_query_last-Ls))
        #then get the first value, for that Mars year
        MY_beg=MY_last.copy()
        #try the mars year of the last time step
        Ls_query_beg=Ls_query_360[0]+(MY_beg-1)*360.
        ti_beg=np.argmin(np.abs(Ls_query_beg-Ls))

        #if the begining value is higher, search in the year before for ti_beg
        if ti_beg>=ti_last:
            MY_beg-=1
            Ls_query_beg=Ls_query_360[0]+(MY_beg-1)*360.
            ti_beg=np.argmin(np.abs(Ls_query_beg-Ls))


        ti=np.arange(ti_beg,ti_last+1)

        Ls_bounds=[Ls[ti[0]],Ls[ti[-1]]] #this is for display
        txt_time=', Ls= avg [(MY%2i) %.2f <-> (MY%2i) %.2f]'%(MY_beg,np.mod(Ls_bounds[0],360.),MY_last,np.mod(Ls_bounds[1],360.))


    return ti,txt_time

#======================================================
#                  TEMPLATE UTILITIES
#======================================================

def filter_input(txt,typeIn='char'):
    '''
    Read Template for the type of data expected
    Args:
        txt: a string, typical the right-hand sign of an equal sign '3', '3,4', or 'all'
        typeIn: type of data expected: 'char', 'float', 'int', 'bool'
    Returns:
        out: float or 1D array [val1,val2] in the expected format

    '''
    if txt =='None' or not txt: #None or empty string
        return None

    if "," in txt: #two values are provided
        answ = []
        for i in range(0,len(txt.split(','))):
            #== For a 'char', read all text as one
            #if typeIn=='char': answ.append(txt.split(',')[i].strip())
            if typeIn=='char': answ= txt
              #====
            if typeIn=='float':answ.append(np.float(txt.split(',')[i].strip()))
            if typeIn=='int':  answ.append(np.int(txt.split(',')[i].strip()))
            if typeIn=='bool': answ.append(txt.split(',')[i].strip()=='True')
        return answ
    else:
        if typeIn=='char':
            answ= txt
        if typeIn=='bool':
            answ=  ('True'==txt)
        #for float and int type, pass the 'all' key word as -99999
        if typeIn=='float':
            if txt=='all':
                answ= -99999.
            elif txt=='AXIS':
                answ= -88888.
            else:
                answ= np.float(txt)
        if typeIn=='int':
            if txt=='all':
                answ= -99999
            else:
                answ=  np.int(txt)
  #would be True is text matches
        return answ

def rT(typeIn='char'):
    '''
    Read Template for the type of data expected
    Args:
        typeIn: type of data expected: 'char', 'float', 'int', 'bool'
    Returns:
        out: float or 1D array [val1,val2] in the expected format

    '''
    global customFileIN
    raw_input=customFileIN.readline()


    #get text on the right side of the equal sign if there is only one  equal '=' sign
    if len(raw_input.split('='))==2:
        txt=raw_input.split('=')[1].strip()

    #---read the string manually if there is more than one'=' signs: e.g '02400.atmos_average2{lat =20}'
    elif len(raw_input.split('='))>2:
        current_varfull='';record=False
        for i in range(0,len(raw_input)):
            if record: current_varfull+=raw_input[i]
            if raw_input[i]=='=': record=True
        txt=current_varfull.strip()

    return  filter_input(txt,typeIn)




def read_axis_options(axis_options_txt):
    '''
    Return axis customization options
    Args:
        axis_options_txt: One liner string: 'Axis Options  : lon = [5,8] | lat = [None,None] | cmap = jet | scale= lin | proj = cart'
    Returns:
        Xaxis: X-axis bounds as a numpy array or None if undedefined
        Yaxis: Y-axis bounds as a numpy array or None if undedefined
        custom_line1: string, i.e colormap ('jet', 'nipy_spectral') or line options, e.g '--r' for dashed red
        custom_line2: lin or log
        custom_line3: None of string for projections, e.g 'ortho -125,45'

    '''
    list_txt=axis_options_txt.split(':')[1].split('|')
    #Xaxis: get bound
    txt=list_txt[0].split('=')[1].replace('[','').replace(']','')
    Xaxis=[]
    for i in range(0,len(txt.split(','))):
        if txt.split(',')[i].strip()=='None':
            Xaxis=None
            break
        else:
            Xaxis.append(np.float(txt.split(',')[i].strip()))
    #Yaxis: get bound
    txt=list_txt[1].split('=')[1].replace('[','').replace(']','')
    Yaxis=[]
    for i in range(0,len(txt.split(','))):
        if txt.split(',')[i].strip()=='None':
            Yaxis=None
            break
        else:
            Yaxis.append(np.float(txt.split(',')[i].strip()))
    #Line or colormap
    custom_line1=list_txt[2].split('=')[1].strip()
    custom_line2=None
    custom_line3=None
    # Scale: lin or log (2D plots only)

    if len(list_txt)==4:
        custom_line2=list_txt[3].split('=')[1].strip()
        if custom_line2.strip()=='None':custom_line2=None
    if len(list_txt)==5:
        custom_line2=list_txt[3].split('=')[1].strip()
        custom_line3=list_txt[4].split('=')[1].strip()
        if custom_line2.strip()=='None':custom_line2=None
        if custom_line3.strip()=='None':custom_line3=None
    return Xaxis, Yaxis,custom_line1,custom_line2,custom_line3


def split_varfull(varfull):
    '''
    Split  the varfull object into its different components.
    Args:
        varfull: a varfull object, for example 'atmos_average@2.zsurf',
                                               '02400.atmos_average@2.zsurf'
    Returns:
        sol_array: a sol number e.g 2400 or None if none is provided
        filetype:  file type, i.e 'atmos_average'
        var:       variable of interest, i.e 'zsurf'
        simuID:    int, simulation ID = 2-1= 1 as Python indexes start at zero

    '''

    #---Default case: no sols number is provided, e.g 'atmos_average2.zsurf'--
    #extract variables and file from varfull

    if varfull.count('.')==1: # atmos_average2.zsurf'
        sol_array=np.array([None])
        filetypeID=varfull.split('.')[0].strip() #file and ID
        var=varfull.split('.')[1].strip()        #variable name
    #---A sol number is profided, e.g '02400.atmos_average2.zsurf'
    elif varfull.count('.')==2:
        sol_array=np.array([int(varfull.split('.')[0].strip())])   #sol number
        filetypeID=varfull.split('.')[1].strip() #file and ID
        var=varfull.split('.')[2].strip()        #variable name
    # Split filename and simulation ID

    if '@' in filetypeID:
        filetype=filetypeID.split('@')[0].strip()
        simuID=int(filetypeID.split('@')[1].strip() )-1 #simulation ID  starts at zero in the code
    else: #no digit, i.e reference simulation
        simuID=0
        filetype=filetypeID
    return sol_array,filetype,var,simuID


def remove_whitespace(raw_input):
    '''
    Remove the white space inside an expression. This is different from the '.strip()' method that only remove white spaces at the edges of the string
    Args:
        raw_input: a string, e.g '[atmos_average.temp] +  2'
    Returns:
        processed_input  the string without white spaces, e.g [atmos_average.temp]+2'

    '''
    processed_input=''
    for i in range(0,len(raw_input)):
        if raw_input[i]!=' ': processed_input+=raw_input[i]
    return processed_input

def clean_comma_whitespace(raw_input):
    '''
    Remove the commas and white spaces inside an expression.
    Args:
        raw_input: a string, e.g 'lat=3. ,'
    Returns:
        processed_input  the string without white spaces or commas e.g 'lat=3.lon=2lev=10.'

    '''
    processed_input=''
    for i in range(0,len(raw_input)):
        if raw_input[i]!=',': processed_input+=raw_input[i]
    return remove_whitespace(processed_input)


def get_list_varfull(raw_input):
    '''
    Given an expression object with '[]' return the different variable needed
    Args:
        raw_input: a complex varfull object, for example '2*[atmos_average.temp]+[atmos_average2.ucomp]*1000'
    Returns:
        var_list  a list of variable to load, e.g ['atmos_average.temp', 'atmos_average2.ucomp']

    '''
    var_list=[]
    record = False
    current_name=''
    for i in range(0,len(raw_input)):
        if raw_input[i]==']':
            record=False
            var_list.append(current_name.strip())
            current_name=''
        if record: current_name+=raw_input[i]
        if raw_input[i]=='[': record=True
    return var_list

def get_overwrite_dim_2D(varfull_bracket,plot_type,fdim1,fdim2,ftod):
    '''
    Given a single varfull object with '{}' return the new dimensions to overwrite the default dimensions
    Args:
        varfull_bracket: a  varfull object with any of the following atmos_average.temp{lev=10;ls=350;lon=155;lat=25} (brackets and semi-colons separated)
        plot_type: the type of plot

    Returns:
        varfull: the varfull without brackets: e.g 'atmos_average.temp'
        fdim_out1,fdim_out1,ftod_out: the dimensions to update
    NOTE:
    2D_lon_lat:   fdim1=ls
                  fdim2=lev

    2D_lat_lev: fdim1=ls
                  fdim2=lon

    2D_time_lat: fdim1=lon
                  fdim2=lev

    2D_lon_lev: fdim1=ls
                  fdim2=lat

    2D_time_lev:fdim1=lat
                  fdim2=lon

    2D_lon_time:  fdim1=lat
                  fdim2=lev
    '''
    #Initialization: use the dimension provided in the template
    fdim_out1=fdim1; fdim_out2=fdim2
    varfull_no_bracket=varfull_bracket.split('{')[0].strip()    #left of the '{' character
    overwrite_txt=remove_whitespace(varfull_bracket.split('{')[1][:-1])  #right of the'{' character, with the last '}' removed
    ndim_update=overwrite_txt.count('=') #count the number of '=' in the string
    split_dim=overwrite_txt.split(';');  #split to different blocs e.g 'lat =3.' and 'lon=20'
    if overwrite_txt.count(';')<overwrite_txt.count('=')-1: prYellow("""*** Error:, use semicolon ';' to separate dimensions '{}'""")
    for i in range(0,ndim_update):
        #Check if the requested dimension exists:
        if split_dim[i].split('=')[0] not in ['ls','lev','lon','lat','tod']:
            prYellow("""*** Warning***, ignoring dimension: '"""+split_dim[i].split('=')[0]+"""' not recognized: must be 'ls','lev','lon', 'lat' or 'tod'""")

        if plot_type=='2D_lon_lat':
            if split_dim[i].split('=')[0]=='ls' :fdim_out1=filter_input(split_dim[i].split('=')[1],'float')
            if split_dim[i].split('=')[0]=='lev': fdim_out2=filter_input(split_dim[i].split('=')[1],'float')
        if plot_type=='2D_lat_lev':
            if split_dim[i].split('=')[0]=='ls':fdim_out1=filter_input(split_dim[i].split('=')[1],'float')
            if split_dim[i].split('=')[0]=='lon': fdim_out2=filter_input(split_dim[i].split('=')[1],'float')
        if plot_type=='2D_time_lat':
            if split_dim[i].split('=')[0]=='lon': fdim_out1=filter_input(split_dim[i].split('=')[1],'float')
            if split_dim[i].split('=')[0]=='lev': fdim_out2=filter_input(split_dim[i].split('=')[1],'float')
        if plot_type=='2D_lon_lev':
            if split_dim[i].split('=')[0]=='ls':fdim_out1=filter_input(split_dim[i].split('=')[1],'float')
            if split_dim[i].split('=')[0]=='lat': fdim_out2=filter_input(split_dim[i].split('=')[1],'float')
        if plot_type=='2D_time_lev':
            if split_dim[i].split('=')[0]=='lat': fdim_out1=filter_input(split_dim[i].split('=')[1],'float')
            if split_dim[i].split('=')[0]=='lon': fdim_out2=filter_input(split_dim[i].split('=')[1],'float')
        if plot_type=='2D_lon_time':
            if split_dim[i].split('=')[0]=='lat': fdim_out1=filter_input(split_dim[i].split('=')[1],'float')
            if split_dim[i].split('=')[0]=='lev': fdim_out2=filter_input(split_dim[i].split('=')[1],'float')

        #Always get tod
        ftod_out=None
        if split_dim[i].split('=')[0]=='tod': ftod_out=filter_input(split_dim[i].split('=')[1],'float')
    # NOTE: filter_input() convert the text '3' or '4,5' to real variable, e.g numpy.array([3.]) numpy.array([4.,5.])
    return varfull_no_bracket, fdim_out1, fdim_out2,ftod_out

def get_overwrite_dim_1D(varfull_bracket,t_in,lat_in,lon_in,lev_in,ftod_in):
    '''
    Given a single varfull object with '{}' return the new dimensions to overwrite the default dimensions
    Args:
        varfull_bracket: a  varfull object with any of the following atmos_average.temp{lev=10;ls=350;lon=155;lat=25;tod=15}
        t_in,lat_in,lon_in,lev_in,ftod_in: the variables as defined by self.t ,self.lat,self.lon,self.lev,self.ftod

    Returns:
        varfull the varfull without brackets: e.g 'atmos_average.temp'
        t_out,lat_out,lon_out,lev_out,ftod_out: the dimensions to update
    NOTE:

    '''
    #Initialization: use the dimension provided in the template
    t_out=t_in; lat_out=lat_in; lon_out=lon_in;lev_out=lev_in
    varfull_no_bracket=varfull_bracket.split('{')[0].strip()    #left of the '{' character
    overwrite_txt=remove_whitespace(varfull_bracket.split('{')[1][:-1])  #right of the'{' character, with the last '}' removed
    ndim_update=overwrite_txt.count('=') #count the number of '=' in the string
    split_dim=overwrite_txt.split(';');  #split to different blocs e.g 'lat =3.' and 'lon=20'
    for i in range(0,ndim_update):
        #Check if the requested dimension exists:
        if split_dim[i].split('=')[0] not in ['time','lev','lon','lat','tod']:
            prYellow("""*** Warning***, ignoring dimension: '"""+split_dim[i].split('=')[0]+"""' not recognized: must be 'time','lev','lon', 'lat' or 'tod'""")


        if split_dim[i].split('=')[0]=='ls':t_out=  filter_input(split_dim[i].split('=')[1],'float')
        if split_dim[i].split('=')[0]=='lat': lat_out=filter_input(split_dim[i].split('=')[1],'float')
        if split_dim[i].split('=')[0]=='lon': lon_out=filter_input(split_dim[i].split('=')[1],'float')
        if split_dim[i].split('=')[0]=='lev': lev_out=filter_input(split_dim[i].split('=')[1],'float')

        #Always get tod
        ftod_out=None
        if split_dim[i].split('=')[0]=='tod': ftod_out=filter_input(split_dim[i].split('=')[1],'float')
    # NOTE: filter_input() convert the text '3' or '4,5' to real variable, e.g numpy.array([3.]) numpy.array([4.,5.])

    return varfull_no_bracket, t_out,lat_out,lon_out,lev_out,ftod_out


def create_exec(raw_input,varfull_list):
    expression_exec=raw_input
    for i in range(0,len(varfull_list)):
        swap_txt='['+varfull_list[i]+']'
        expression_exec=expression_exec.replace(swap_txt,'VAR[%i]'%(i))
    return expression_exec

def fig_layout(subID,nPan,vertical_page=False):
    '''
    Return figure layout
    Args:
        subID:    integer, current subplot number
        nPan : integer, number of panels desired on the figure, up to 64 (8x8 panel)
        vertical_page: if True, reverse the tuple for vertical layout
    Returns:
        out: tuple with approriate layout: plt.subplot(nrows=out[0],ncols=out[1],plot_number=out[2])
    '''
    out=list((0,0,0)) #initialization

    if nPan==1:layout=(1,1) #nrow,ncol
    if nPan==2:layout=(1,2)
    if nPan==3 or nPan==4 :layout=(2,2)
    if nPan==5 or nPan==6 :layout=(2,3)
    if nPan==7 or nPan==8 :layout=(2,4)
    if nPan==9:            layout=(3,3)
    if 10<=nPan<=12:layout=(3,4)
    if 13<=nPan<=16:layout=(4,4)
    if 17<=nPan<=20:layout=(4,5)
    if 21<=nPan<=25:layout=(5,5)
    if 26<=nPan<=30:layout=(5,6)
    if 30<=nPan<=36:layout=(6,6)
    if 36<=nPan<=42:layout=(7,6)
    if 42<=nPan<=49:layout=(7,7)
    if 49<=nPan<=56:layout=(8,7)
    if 56<=nPan<=64:layout=(8,8)
    if vertical_page:layout=layout[::-1]

    #finally the current plot
    out[0:2]=layout
    out[2]=subID

    return out

def make_template():
    global customFileIN # (will be modified)
    global current_version
    newname=output_path+'/Custom.in'
    newname= create_name(newname)

    customFileIN=open(newname,'w')

    lh="""# """ #Add a line header. This is primary use to change the coloring of the text when using vim
    #==============Create header with instructions, and add the version number to the title====
    customFileIN.write("===================== |MarsPlot V%s|===================\n"%(current_version))
    if parser.parse_args().template: #Additional instructions if requested
        customFileIN.write(lh+"""QUICK REFERENCE:\n""")
        customFileIN.write(lh+"""> Find the matching  template for the desired plot type. Do not edit any labels left of any '=' sign \n""")
        customFileIN.write(lh+"""> Duplicate/remove any of the <<<< blocks>>>>, skip by setting <<<< block = False >>>> \n""")
        customFileIN.write(lh+"""> 'True', 'False' and 'None' are capitalized. Do not use quotes '' anywhere in this file \n""")
        customFileIN.write(lh+"""> Cmin, Cmax define the colorbar range. Scientific notation (e.g. 1e-6, 2e3) is supported \n""")
        customFileIN.write(lh+"""       If more than 2 values are provided (e.g. 150,200,250) those define the shaded contours \n""")
        customFileIN.write(lh+"""> Solid contours for the 2nd variable are always provided as list, e.g.:  150,200,250 \n""")
        customFileIN.write(lh+"""> 'Level' refers to either 'level','pfull', 'pstd' in [Pa], 'zstd' or 'zagl' [m] or 'zgrid' [m], depending on the type of *.nc file\n""")
        customFileIN.write(lh+"""FREE DIMENSIONS:\n""")
        customFileIN.write(lh+"""> Use 'Dimension = 55.' to set to the closest value\n""")
        customFileIN.write(lh+"""> Use 'Dimension = all' to average over all values\n""")
        customFileIN.write(lh+"""> Use 'Dimension = -55.,55.' to get the average between -55. and 55. \n""")
        customFileIN.write(lh+"""> 'None' refers to the default setting for that Dimension: \n""")
        customFileIN.write(lh+"""    -A) time  = instant time step at Nt (i.e last timestep) \n""")
        customFileIN.write(lh+"""    -B) lev   = sfc (e.g., Nz for *.nc files and 0 for *_pstd.nc files) \n""")
        customFileIN.write(lh+"""    -C) lat   = equator slice \n""")
        customFileIN.write(lh+"""    -D) lon   = 'all', i.e zonal average over all longitudes\n""")
        customFileIN.write(lh+"""    -E) tod   = '15', i.e. 3pm UT \n""")
        customFileIN.write(lh+"""> Overwrite the dimensions using atmos_average.temp{ls = 90 ; lev= 5.,10; lon= all ; lat=45} Use brackets '{}' and SEMI-COLONS ';'\n""")
        customFileIN.write(lh+"""     Specific Time Of Day (tod) in diurn files are accessed with brackets, '{}', e.g. atmos_diurn.ps{tod = 20} \n""")
        customFileIN.write(lh+""">    Units must be the same as the free dimension block, i.e time [Ls], lev [Pa/m], lon [+/-180 deg], and lat [deg]   \n""")
        customFileIN.write(lh+"""TIME SERIES AND 1D PLOTS:\n""")
        customFileIN.write(lh+"""> Use 'Dimension = AXIS' to set the varying axis\n""")
        customFileIN.write(lh+"""> The other free dimensions accept value, 'all' or 'valmin, valmax' as above\n""")
        customFileIN.write(lh+"""> The 'Diurnal [hr]' option may only be set to 'AXIS' or 'None', use the 'tod' syntax as above  \n""")
        customFileIN.write(lh+""">    to request specific time of day, for all other plots (i.e. atmos_diurn.ps{tod = 20}) \n""")
        customFileIN.write(lh+"""AXIS OPTIONS AND PROJECTIONS:\n""")
        customFileIN.write(lh+"""Set the x-axis and y-axis limits in the figure units. All Matplolib styles are supported:\n""")
        customFileIN.write(lh+"""> 'cmap' changes the colormap: 'jet' (winds), 'nipy_spectral' (temperature), 'bwr' (diff plot)\n""")
        customFileIN.write(lh+"""> 'line' sets the line style:  '-r' (solid red), '--g' (dashed green), '-ob' (solid & blue markers)\n""")
        customFileIN.write(lh+"""> 'scale' sets the color mapping:  'lin' (linear) or 'log' (logarithmic) For 'log', Cmin,Cmax are typically expected \n""")
        customFileIN.write(lh+"""> 'proj' sets the projection: Cylindrical options are 'cart' (cartesian), 'robin'  (Robinson), 'moll' (Mollweide) \n""")
        customFileIN.write(lh+""">                             Azimuthal   options are 'Npole' (north pole), 'Spole' (south pole), 'ortho' (Orthographic)  \n""")
        customFileIN.write(lh+""">  Azimutal projections accept customization arguments: 'Npole lat_max', 'Spole lat_min' , 'ortho lon_center, lat_center' \n""")
        customFileIN.write(lh+"""KEYWORDS:\n""")
        customFileIN.write(lh+"""> 'HOLD ON' [blocks of figures] 'HOLD OFF' groups the figures as a multi-panel page  \n""")
        customFileIN.write(lh+"""  (Optional: use 'HOLD ON 2,3' to force a 2 lines 3 column layout) \n""")
        customFileIN.write(lh+"""> [line plot 1] 'ADD LINE' [line plot 2] adds similar 1D-plots on the same figure)\n""")
        customFileIN.write(lh+"""> 'START' and (optionally) 'STOP' can be used to conveniently skip plots below. Use '#' to add comments. \n""")
        customFileIN.write(lh+"""ALGEBRA AND CROSS-SIMULATIONS PLOTS:\n""")
        customFileIN.write(lh+"""Use 'N>' to add a Nth simulation with matching timesteps to the <<< Simulations >>> block (e.g.  4>, 5>...)  \n""")
        customFileIN.write(lh+"""Use full path, e.g. '2> /u/akling/FV3/verona/simu2/history' Empty fields are ignored, comment out with '#' \n""")
        customFileIN.write(lh+"""A variable 'var' in a 'XXXXX.file.nc' from this Nth simulation is accessed using the '@' symbol and 'XXXXX.file@N.var' syntax \n""")
        customFileIN.write(lh+"""Encompass raw outputs with square brackets '[]' for element-wise operations, e.g: \n""")
        customFileIN.write(lh+"""> '[fixed.zsurf]/(10.**3)'                              (convert topography from [m] to [km])\n""")
        customFileIN.write(lh+"""> '[atmos_average.taudust_IR]/[atmos_average.ps]*610' (normalize the dust opacity)     \n""")
        customFileIN.write(lh+"""> '[atmos_average.temp]-[atmos_average@2.temp]'    (temp. difference between ref simu and simu 2)\n""")
        customFileIN.write(lh+"""> '[atmos_average.temp]-[atmos_average.temp{lev=10}]'   (temp. difference between the default (near surface) and the 10 Pa level\n""")

        customFileIN.write(lh+"""        Supported expressions are: sqrt, log, exp, abs, min, max, mean \n""")
    customFileIN.write("<<<<<<<<<<<<<<<<<<<<<< Simulations >>>>>>>>>>>>>>>>>>>>>\n")
    customFileIN.write("ref> None\n")
    customFileIN.write("2> \n")
    customFileIN.write("3>\n")
    customFileIN.write("=======================================================\n")
    customFileIN.write("START\n")
    customFileIN.write("\n") #new line
    #===============================================================
    #For the default list of figures in main(), create a  template.
    for i in range(0,len(objectList)):
        if objectList[i].subID==1 and objectList[i].nPan>1: customFileIN.write('HOLD ON\n')
        objectList[i].make_template()
        customFileIN.write('\n')
        if objectList[i].nPan>1 and objectList[i].subID==objectList[i].nPan: customFileIN.write('HOLD OFF\n')

        #Separate the empty templates
        if  i==1:
            customFileIN.write("""#=========================================================================\n""")
            customFileIN.write("""#================== Empty Templates (set to False)========================\n""")
            customFileIN.write("""#========================================================================= \n""")
            customFileIN.write(""" \n""")



    customFileIN.close()

    # NAS system only: set group permission to the file and print completion message
    give_permission(newname)
    print(newname +' was created ')
    #---

def give_permission(filename):
    # NAS system only: set group permission to the file
    try:
        subprocess.check_call(['setfacl -v'],shell=True,stdout=open(os.devnull, "w"),stderr=open(os.devnull, "w")) #catch error and standard output
        cmd_txt='setfacl -R -m g:s0846:r '+filename
        subprocess.call(cmd_txt,shell=True)
    except subprocess.CalledProcessError:
        pass

def namelist_parser(Custom_file):
    '''
    Parse a template
    Args:
        Custom_file: full path to Custom.in file
    Actions:
        Update  global variableFigLayout, objectList
    '''
    global objectList
    global customFileIN
    global input_paths
    # A Custom file is provided, flush the default figures defined in main()
    #---
    objectList=[] #all individual plots

    panelList=[] #list of panels
    subplotList=[] #layout of figures
    addLineList=[] #add several line plot on the same graphs
    layoutList=[]
    nobj=0        #number for the object: e.g 1,[2,3],4... with 2 & 3 plotted as a two panels plot
    npanel=1      #number of panels ploted along this object, e.g: '1' for object #1 and '2' for the objects #2 and #3
    subplotID=1  #subplot ID per object: e.g '1' for object #1, '1' for object #2 and '2' for object #3
    holding=False
    addLine=False
    addedLines=0  #line plots
    npage=0       #plot number at the begining of a new page (e.g 'HOLD ON')
    layout =None  #Used if layout is provided with HOLD ON (e.g. HOLD ON 2,3')

    customFileIN=open(Custom_file,'r')
    #===Get version in the header====
    version=np.float(customFileIN.readline().split('|')[1].strip().split('V')[1].strip())
    # Check if the main versions are compatible,  (1.1 and 1.2 are OK but not 1.0 and 2.0)
    if np.int(version)!=np.int(current_version):
         prYellow('*** Warning ***')
         prYellow('Using MarsPlot V%s but Custom.in template is depreciated (using V%s)'%(current_version,version))
         prYellow('***************')

    #==========Skip the header======
    while (customFileIN.readline()[0]!='<'):
        pass
    #==========Read simulations in <<<<<<<<<< Simulations >>>>>> ======
    while True:
        line=customFileIN.readline()
        if line[0]=='#': #skip comment
            pass
        else:
            if line[0]=='=': break #finished reading
            # Special case reference simulation
            if line.split('>')[0]=='ref':
                # if is different from default, overwrite it
                if line.split('>')[1].strip()!='None':
                    input_paths[0]=line.split('>')[1].strip()
            else:
                if '>' in line: #line contains '>' symbol
                    if line.split('>')[1].strip(): #line exist and is not blank
                        input_paths.append(line.split('>')[1].strip())

    #===========skip lines until the kweyword 'START' is found================
    nsafe=0 #initialize counter for safety
    while True and nsafe<2000:
        line=customFileIN.readline()
        if line.strip()=='START':break
        nsafe+=1
    if nsafe==2000:prRed(""" Custom.in is missing a 'START' keyword after the '=====' simulation block""")

    #=============Start reading the figures=================
    while True:
        line=customFileIN.readline()

        if not line or line.strip()=='STOP':
            break #Reached End Of File

        if line.strip()[0:7]=='HOLD ON':
            holding=True
            subplotID=1

            #Get layout info
            if ',' in line: # layout is provided, e.g. 'HOLD ON 2,3'
                tmp= line.split('ON')[-1].strip()  # this returns '2,3' as a  string
                layout=[int(tmp.split(',')[0]),int(tmp.split(',')[1])] #This returns [2,3]
            else:
                layout=None
        #adding a 1D plot to an existing line plot
        if line.strip()=='ADD LINE':
            addLine=True

        if line[0]== '<': #If new figure
            figtype,boolPlot=get_figure_header(line)
            if boolPlot : #only if we want to plot the field
            #Add object to the list
                if figtype =='Plot 2D lon X lat'   :objectList.append(Fig_2D_lon_lat())
                if figtype =='Plot 2D time X lat'  :objectList.append(Fig_2D_time_lat())
                if figtype =='Plot 2D lat X lev' :objectList.append(Fig_2D_lat_lev())
                if figtype =='Plot 2D lon X lev' :objectList.append(Fig_2D_lon_lev())
                if figtype =='Plot 2D time X lev':objectList.append(Fig_2D_time_lev())
                if figtype =='Plot 2D lon X time'  :objectList.append(Fig_2D_lon_time())
                if figtype =='Plot 1D'             :objectList.append(Fig_1D())
                objectList[nobj].read_template()
                nobj+=1
                #====debug only===========
                #print('------nobj=',nobj,' npage=',npage,'-------------------')

                #===================
                if holding and not addLine:
                    subplotList.append(subplotID)
                    panelList.append(subplotID)
                    subplotID+=1
                    #Add +1 panel to all plot in current page
                    for iobj in range(npage,nobj-1):
                        panelList[iobj]+=1

                elif holding and addLine:
                    #Do not update  subplotID if we are adding lines
                    subplotList.append(subplotID-1)
                    panelList.append(subplotID-1)

                else :
                    #We are not holding: there is a single panel per page and we reset the page counter
                    panelList.append(1)
                    subplotList.append(1)
                    npage=nobj
                    layout=None

                if layout:
                    layoutList.append(layout)
                else:
                    layoutList.append(None)

                #====================

                if addLine:
                    addedLines+=1
                    addLineList.append(addedLines)
                else:
                     addLineList.append(0) #no added lines
                     addedLines=0 #reset line counter

                #====debug only====
                #for ii in range(0,len(   subplotList)):
                #    prCyan('[X,%i,%i,%i]'%(subplotList[ii],panelList[ii],addLineList[ii]))
                #=================


                #============Depreciated=(old way to attribute the plot numbers without using npage)=============
                # if holding:
                #     subplotList.append(subplotID-addedLines)
                #     panelList.append(subplotID-addedLines)
                #     if not addLine:
                #         # add +1 to the number of panels for the previous plots
                #         n=1
                #         while n<=subplotID-1:
                #             panelList[nobj-n-1]+=1 #print('editing %i panels, now %i'%(subplotID-1,nobj-n-1))
                #             n+=1
                #     subplotID+=1
                # else :
                #     panelList.append(1)
                #     subplotList.append(1)
                #========================================================


            addLine=False #reset after reading each block
        if line.strip()=='HOLD OFF':
            holding=False
            subplotID=1
            npage=nobj



    #Make sure we are not still holding figures
    if holding:
        prRed('*** Error ***')
        prRed("""Missing 'HOLD OFF' statement in """+Custom_file)
        exit()
    #Make sure we are not still holding figures
    if addLine:
        prRed('*** Error ***')
        prRed("""Cannot have 'ADD LINE' after the last figure in """+Custom_file)
        exit()
    #Finished reading the file, attribute the right number of figure and panels for each plot
    #print('=======Summary=========')
    for i in range(0,nobj):
        objectList[i].subID=subplotList[i]
        objectList[i].nPan=panelList[i]
        objectList[i].addLine=addLineList[i]
        objectList[i].layout=layoutList[i]

        #==debug only====
        #prPurple('%i:[%i,%i,%i]'%(i,objectList[i].subID,objectList[i].nPan,objectList[i].addLine))
    customFileIN.close()


def get_figure_header(line_txt):
    '''
    This function return the type of a figure and tells us if wanted
    Args:
        line_txt: string, figure header from Custom.in, i.e '<<<<<<<<<<<<<<| Plot 2D lon X lat = True |>>>>>>>>>>>>>'
    Returns:
        figtype : string, figure type, i.e:  Plot 2D lon X lat
        boolPlot: boolean, is the plot wanted?
    '''
    line_cmd=line_txt.split('|')[1].strip() #Plot 2D lon X lat = True
    figtype=line_cmd.split('=')[0].strip()  #Plot 2D lon X lat
    boolPlot=line_cmd.split('=')[1].strip()=='True' # Return True
    return figtype, boolPlot


def format_lon_lat(lon_lat,type):
    '''
    Format latitude and longitude as labels, e.g. 30S , 30N, 45W, 45E
    Args:
        lon_lat (float): latitude or longitude +/-180
        type (string) : 'lat' or 'lon'
    Returns:
        lon_lat_label : (string), formatted label
    '''
    #Initialize
    letter=""
    if type =='lon':
        if lon_lat<0:letter="W"
        if lon_lat>0:letter="E"
    elif type =='lat':
        if lon_lat<0:letter="S"
        if lon_lat>0:letter="N"
    #Remove minus sign, if any
    lon_lat=abs(lon_lat)
    return "%i%s" %(lon_lat,letter)


#======================================================
#                  FILE SYSTEM UTILITIES
#======================================================


def get_Ncdf_num():
    '''
    Get the sol numbers of all the netcdf files in directory
    This test is based on the existence of a least one  XXXXX.fixed.nc in the current directory.
    Args:
        None
    Returns:
        Ncdf_num: a sorted array of sols
    '''
    list_dir=os.listdir(input_paths[0])
    avail_fixed = [k for k in list_dir if '.fixed.nc' in k] #e.g. '00350.fixed.nc', '00000.fixed.nc'
    list_num = [item[0:5] for item in avail_fixed]          #remove .fixed.nc, e.g. '00350', '00000'
    Ncdf_num=np.sort(np.asarray(list_num).astype(np.float)) # transform to array, e.g. [0, 350]
    if Ncdf_num.size==0:Ncdf_num= None
    #    print("No XXXXX.fixed.nc detected in "+input_paths[0])
    #    raise SystemExit #Exit cleanly
    return Ncdf_num

def select_range(Ncdf_num,bound):
    '''
    Args:
        Ncdf_num:  a sorted array of sols
        bound: a integer representing a date (e.g. 0350) or an array containing the sol bounds (e.g [min max])
    Returns:
        Ncdf_num: a sorted array of sols within the prescribed bounds
    '''
    bound=np.array(bound)
    if bound.size==1:
        Ncdf_num=Ncdf_num[Ncdf_num==bound]
        if Ncdf_num.size==0:
            prRed('*** Error ***')
            prRed("File %05d.fixed.nc not detected"%(bound))
            exit()
    elif bound.size==2:
        Ncdf_num=Ncdf_num[Ncdf_num>=bound[0]]
        Ncdf_num=Ncdf_num[Ncdf_num<=bound[1]]
        if Ncdf_num.size==0:
            prRed('*** Error ***')
            prRed("No XXXXX.fixed.nc detected between sols [%05d-%05d] please check date range"%(bound[0],bound[1]))
            exit()
    return Ncdf_num

def create_name(root_name):
    '''
    Create a file name based on its existence in the current directory.
    Args:
        root_name: desired name for the file: "/path/custom.in" or "/path/figure.png"
    Returns:
        new_name: new name if the file already exists: "/path/custom_01.in" or "/path/figure_01.png"
    '''
    n=1
    len_ext=len(root_name.split('.')[-1]) #get extension lenght (e.g 2 for *.nc, 3 for *.png)
    ext=root_name[-len_ext:]              #get extension
    new_name=root_name #initialization
    #if example.png already exist, create example_01.png
    if os.path.isfile(new_name):
        new_name=root_name[0:-(len_ext+1)]+'_%02d'%(n)+'.'+ext
    #if example_01.png already exist, create example_02.png etc...
    while os.path.isfile(root_name[0:-(len_ext+1)]+'_%02d'%(n)+'.'+ext):
        n=n+1
        new_name=root_name[0:-(len_ext+1)]+'_%02d'%(n)+'.'+ext
    return new_name


def path_to_template(custom_name):
    '''
    Create a file name based on its existence in the current directory.
    Args:
        custom_name: custom file name, accepted formats are my_custom or my_custom.in
    Returns:
        full_path: full_path to /u/user/FV3/templates/my_custom.in

         If file not found, try shared directory
    '''
    local_dir=sys.prefix+'/mars_templates'

    #---
    custom_name=custom_name[0] #convert the 1-element list to a string
    if custom_name[-3:]!='.in':  custom_name=custom_name+'.in'#add extension if not provided
    #first look in  '~/FV3/templates'
    if not os.path.isfile(local_dir+'/'+custom_name):
        #then look in  '/lou/s2n/mkahre/MCMC/analysis/working/templates'
        if not os.path.isfile(shared_dir+'/'+custom_name):
            prRed('*** Error ***')
            prRed('File '+custom_name+' not found in '+local_dir+' ... nor in : \n                          '+shared_dir)
            # if a local ~/FV3/templates path does not exist, suggest to create it
            if not os.path.exists(local_dir):
                prYellow('Note: directory: ~/FV3/templates'+' does not exist, create it with:')
                prCyan('mkdir '+local_dir)
            exit()
        else:
            return shared_dir+'/'+custom_name
    else:
        return local_dir+'/'+custom_name


def progress(k,Nmax,txt='',success=True):
    """
    Display a progress bar to monitor heavy calculations.
    Args:
        k: current iteration of the outer loop
        Nmax: max iteration of the outer loop
    Returns:
        Running... [#---------] 10.64 %
    """
    import sys
    progress=float(k)/Nmax
    barLength = 10 # Modify this to change the length of the progress bar
    block = int(round(barLength*progress))
    bar = "[{0}]".format( "#"*block + "-"*(barLength-block))
    #bar = "Running... [\033[96m{0}\033[00m]".format( "#"*block + "-"*(barLength-block))  #add color
    if success==True:
        #status="%i %% (%s)"%(100*progress,txt) #no color
        status="%3i %% \033[92m(%s)\033[00m"%(100*progress,txt)  #green
    elif success==False:
        status="%3i %% \033[91m(%s)\033[00m"%(100*progress,txt) #red
    elif success==None:
        status="%3i %% (%s)"%(100*progress,txt) #red
    text='\r'+bar+status+'\n'
    sys.stdout.write(text)
    if not debug: sys.stdout.flush()


def prep_file(var_name,file_type,simuID,sol_array):
    '''
    Given the different information, open the file as a Dataset or MFDataset object.
    Note that the input arguments are typically extracted  from a varfull object, e.g.  '03340.atmos_average.ucomp',
    not a file from those the existence on the disk is known beforehand
    Args:
        var_name: variable to extract, e.g. 'ucomp'
        file_type: 'fixed', atmos_average_pstd
        simuID:    e.g 2 for 2nd simulation
        sol_array: e.g [3340,4008]

    Returns:
        f: Dataset or MFDataset object
        var_info: longname and units
        dim_info: dimensions e.g ('time', 'lat','lon')
        dims:    shape of the array e.g [133,48,96]
    '''
    global input_paths
    global Ncdf_num #global variable that holds  the different sos number, e.g [1500,2400]
    # A specific sol was requested, e.g [2400]
    Sol_num_current = [0] #Set dummy value
    #First check if the file exist on tape without a sol number (e.g. 'Luca_dust_MY24_dust.nc') exists on the disk
    if os.path.isfile(input_paths[simuID]+'/'+file_type+'.nc'):
            file_has_sol_number=False
    # If the file does NOT exist, append sol number as provided by MarsPlot Custom.in -d sol or last file in directory
    else:
        file_has_sol_number=True
        # Two options here: first a file number is explicitly provided in the varfull, e.g. 00668.atmos_average.nc
        if sol_array != [None]:
            Sol_num_current=sol_array
        elif Ncdf_num !=None:
            Sol_num_current =Ncdf_num
    #Creat a list of files for generality (even if only one file is provided)
    nfiles=len(Sol_num_current)
    file_list = [None]*nfiles #initialize the list

    #Loop over the requested time steps
    for i in range(0,nfiles):
        if file_has_sol_number: #include sol number
            file_list[i] = input_paths[simuID]+'/%05d.'%(Sol_num_current[i])+file_type+'.nc'
        else:    #no sol number
            file_list[i] = input_paths[simuID]+'/'+file_type+'.nc'
        check_file_tape(file_list[i],abort=False)
    #We know the files exist on tape, now open it with MFDataset if an aggregation dimension is detected
    try:
        f=MFDataset(file_list, 'r')
    except IOError:
        #This IOError should be :'master dataset ***.nc does not have a aggregation dimension', we will use Dataset otherwise
        f=Dataset(file_list[0], 'r')

    var_info=getattr(f.variables[var_name],'long_name','')+' ['+ getattr(f.variables[var_name],'units','')+']'
    dim_info=f.variables[var_name].dimensions
    dims=f.variables[var_name].shape
    return f, var_info,dim_info, dims

#======================================================
#                  FIGURE DEFINITIONS
#======================================================
class Fig_2D(object):
    # Parent class for 2D figures
    def __init__(self,varfull='fileYYY.XXX',doPlot=False,varfull2=None):

        self.title=None
        self.varfull=varfull
        self.range=None
        self.fdim1=None
        self.fdim2=None
        self.ftod=None  #Time of day
        self.varfull2=varfull2
        self.contour2=None
        # Logic
        self.doPlot=doPlot
        self.plot_type=self.__class__.__name__[4:]

        #Extract filetype, variable, and simulation ID (initialization only for the default plots)
        # Note that the varfull objects for the default plots are simple , e.g are atmos_average.ucomp
        self.sol_array,self.filetype,self.var,self.simuID=split_varfull(self.varfull)
        #prCyan(self.sol_array);prYellow(self.filetype);prGreen(self.var);prPurple(self.simuID)
        if self.varfull2: self.sol_array2,self.filetype2,self.var2,self.simuID2=split_varfull(self.varfull2)

        #Multi panel
        self.nPan=1
        self.subID=1
        self.layout = None # e.g. [2,3], used only if 'HOLD ON 2,3' is used
        #Annotation for free dimensions
        self.fdim_txt=''
        self.success=False
        self.addLine=False
        self.vert_unit='' #m or Pa
        #Axis options

        self.Xlim=None
        self.Ylim=None
        self.axis_opt1='jet'
        self.axis_opt2='lin' #Linear or logscale
        self.axis_opt3=None #place holder for projections

    def make_template(self,plot_txt,fdim1_txt,fdim2_txt,Xaxis_txt,Yaxis_txt):
        customFileIN.write("<<<<<<<<<<<<<<| {0:<15} = {1} |>>>>>>>>>>>>>\n".format(plot_txt,self.doPlot))
        customFileIN.write("Title          = %s\n"%(self.title))             #1
        customFileIN.write("Main Variable  = %s\n"%(self.varfull))           #2
        customFileIN.write("Cmin, Cmax     = %s\n"%(self.range))             #3
        customFileIN.write("{0:<15}= {1}\n".format(fdim1_txt,self.fdim1))    #4
        customFileIN.write("{0:<15}= {1}\n".format(fdim2_txt,self.fdim2))    #4
        customFileIN.write("2nd Variable   = %s\n"%(self.varfull2))          #6
        customFileIN.write("Contours Var 2 = %s\n"%(self.contour2))          #7

        #Write colormap AND projection if plot is of the type 2D_lon_lat
        if self.plot_type=='2D_lon_lat':
            customFileIN.write("Axis Options  : {0} = [None,None] | {1} = [None,None] | cmap = jet | scale = lin | proj = cart \n".format(Xaxis_txt,Yaxis_txt)) #8
        else:
            customFileIN.write("Axis Options  : {0} = [None,None] | {1} = [None,None] | cmap = jet |scale = lin \n".format(Xaxis_txt,Yaxis_txt))    #8

    def read_template(self):
        self.title= rT('char')                   #1
        self.varfull=rT('char')                  #2
        self.range=rT('float')                   #3
        self.fdim1=rT('float')                   #4
        self.fdim2=rT('float')                   #5
        self.varfull2=rT('char')                 #6
        self.contour2=rT('float')                #7
        self.Xlim,self.Ylim,self.axis_opt1,self.axis_opt2,self.axis_opt3=read_axis_options(customFileIN.readline())     #8

        #Various sanity checks
        if self.range and len(np.atleast_1d(self.range))==1:
            prYellow('*** Warning ***, In plot %s, Cmin, Cmax must be two values, resetting to default'%(self.varfull))
            self.range=None

        #Do not Update the variable after reading template

        #self.sol_array,self.filetype,self.var,self.simuID=split_varfull(self.varfull)
        #if self.varfull2: self.sol_array2,self.filetype2,self.var2,self.simuID2=split_varfull(self.varfull2)


    def data_loader_2D(self,varfull,plot_type):

        #Simply plot one of the variable in the file
        if not '[' in varfull:
            #---If overwriting dimensions, get the new dimensions and trim varfull from the '{lev=5.}' part
            if '{' in varfull :
                varfull,fdim1_extract,fdim2_extract,ftod_extract=get_overwrite_dim_2D(varfull,plot_type,self.fdim1,self.fdim2,self.ftod)
                # fdim1_extract,fdim2_extract constains the dimensions to overwrite is '{}' are provided of the default self.fdim1, self.fdim2  otherwise
            else: # no '{ }' use to overwrite the dimensions, copy the plots' defaults
                fdim1_extract,fdim2_extract,ftod_extract=self.fdim1, self.fdim2,self.ftod

            sol_array,filetype,var,simuID=split_varfull(varfull)
            xdata,ydata,var,var_info=self.read_NCDF_2D(var,filetype,simuID,sol_array,plot_type,fdim1_extract,fdim2_extract,ftod_extract)
        #Realize a operation on the variables
        else:
            VAR=[]
            # Extract individual variables and prepare for execution
            varfull=remove_whitespace(varfull)
            varfull_list=get_list_varfull(varfull)
            #Initialize list of requested dimensions;
            fdim1_list=[None]*len(varfull_list)
            fdim2_list=[None]*len(varfull_list)
            ftod_list=[None]*len(varfull_list)
            expression_exec=create_exec(varfull,varfull_list)



            for i in range(0,len(varfull_list)):
                #---If overwriting dimensions, get the new dimensions and trim varfull from the '{lev=5.}' part
                if '{' in varfull_list[i] :
                    varfull_list[i],fdim1_list[i],fdim2_list[i],ftod_list[i]=get_overwrite_dim_2D(varfull_list[i],plot_type,self.fdim1,self.fdim2,self.ftod)
                else: # no '{ }' use to overwrite the dimensions, copy the plots' defaults
                    fdim1_list[i],fdim2_list[i],ftod_list[i]=self.fdim1, self.fdim2,self.ftod

                sol_array,filetype,var,simuID=split_varfull(varfull_list[i])
                xdata,ydata,temp,var_info=self.read_NCDF_2D(var,filetype,simuID,sol_array,plot_type,fdim1_list[i],fdim2_list[i],ftod_list[i])
                VAR.append(temp)
            var_info=varfull
            var=eval(expression_exec)

        return xdata,ydata,var,var_info

    def read_NCDF_2D(self,var_name,file_type,simuID,sol_array,plot_type,fdim1,fdim2,ftod):
        f, var_info,dim_info, dims=prep_file(var_name,file_type,simuID,sol_array)

        #Get the file type ('fixed','diurn', 'average', 'daily') and interpolation type (pfull, zstd etc...)
        f_type,interp_type=FV3_file_type(f)

        #Initialize dimensions (These are in all the .nc files)

        lat=f.variables['lat'][:];lati=np.arange(0,len(lat))
        lon=f.variables['lon'][:];loni=np.arange(0,len(lon))

        #If self.fdim is empty, add the variable name (do only once)
        add_fdim=False
        if not self.fdim_txt.strip():add_fdim=True

        #------------------------Time of Day ----------------------------
        # For diurn files, select data on the time of day axis and update dimensions
        # so the resulting variable is the same as atmos_average and atmos_daily file.
        # Time of day is always the 2nd dimension, i.e. dim_info[1]

        if f_type=='diurn' and dim_info[1][:11]=='time_of_day':
            tod=f.variables[dim_info[1]][:]
            todi,temp_txt =get_tod_index(ftod,tod)
            #Update dim_info from ('time','time_of_day_XX, 'lat', 'lon') to  ('time', 'lat', 'lon')
            # OR ('time','time_of_day_XX, 'pfull','lat', 'lon') to  ('time', 'pfull','lat', 'lon') etc...
            dim_info=(dim_info[0],)+dim_info[2:]

            if add_fdim:self.fdim_txt+=temp_txt
        #-----------------------------------------------------------------------
        #Load variable depending on the requested free dimensions

        #======static======= , ignore level and time dimension
        if dim_info==('lat', 'lon'):
            var=f.variables[var_name][lati,loni]
            f.close()
            return lon,lat,var,var_info

        #======time,lat,lon=======
        if dim_info==('time', 'lat', 'lon'):
        #Initialize dimension
            t=f.variables['time'][:];Ls=np.squeeze(f.variables['areo'][:]);ti=np.arange(0,len(t))
            #For diurn file, change time_of_day(time,24,1) to time_of_day(time) at midnight UT
            if f_type=='diurn'and len(Ls.shape)>1:Ls=np.squeeze(Ls[:,0])
            t_stack=np.vstack((t,Ls)) #stack the time and ls array as one variable

            if plot_type=='2D_lon_lat': ti,temp_txt =get_time_index(fdim1,Ls)
            if plot_type=='2D_time_lat':loni,temp_txt =get_lon_index(fdim1,lon)
            if plot_type=='2D_lon_time':lati,temp_txt =get_lat_index(fdim1,lat)

            if add_fdim:self.fdim_txt+=temp_txt

            #Extract data and close file
            #If diurn, we will do the tod averaging first.
            if f_type=='diurn':
                var=f.variables[var_name][ti,todi,lati,loni].reshape(len(np.atleast_1d(ti)),len(np.atleast_1d(todi)),\
                     len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))
                var=np.nanmean(var,axis=1)
            else:
                var=f.variables[var_name][ti,lati,loni].reshape(len(np.atleast_1d(ti)),len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))
            f.close()
            w=area_weights_deg(var.shape,lat[lati])

            #Return data
            if plot_type=='2D_lon_lat': return lon,lat,np.nanmean(var,axis=0),var_info #time average
            if plot_type=='2D_time_lat':return t_stack,lat,np.nanmean(var,axis=2).T,var_info #transpose, Xdim must be in last column of var
            if plot_type=='2D_lon_time':return lon,t_stack,np.average(var,weights=w,axis=1),var_info


        #======time,level,lat,lon=======
        if (dim_info==('time', 'pfull', 'lat', 'lon')
           or dim_info==('time', 'level', 'lat', 'lon')
           or dim_info==('time', 'pstd', 'lat', 'lon')
           or dim_info==('time', 'zstd', 'lat', 'lon')
           or dim_info==('time', 'zagl', 'lat', 'lon')
           or dim_info==('time', 'zgrid', 'lat', 'lon')):

            if dim_info[1] in ['pfull','level','pstd']:  self.vert_unit='Pa'
            if dim_info[1] in ['zagl','zstd']:  self.vert_unit='m'

            #Initialize dimensions
            levs=f.variables[dim_info[1]][:] #dim_info[1] is either pfull, level, pstd, zstd,zagl or zgrid
            zi=np.arange(0,len(levs))
            t=f.variables['time'][:];Ls=np.squeeze(f.variables['areo'][:]);ti=np.arange(0,len(t))
            #For diurn file, change time_of_day(time,24,1) to time_of_day(time) at midnight UT
            if f_type=='diurn'and len(Ls.shape)>1:Ls=np.squeeze(Ls[:,0])
            t_stack=np.vstack((t,Ls)) #stack the time and ls array as one variable

            if plot_type=='2D_lon_lat':
                ti,temp_txt =get_time_index(fdim1,Ls)
                if add_fdim:self.fdim_txt+=temp_txt
                zi,temp_txt =get_level_index(fdim2,levs)
                if add_fdim:self.fdim_txt+=temp_txt

            if plot_type=='2D_time_lat':
                loni,temp_txt =get_lon_index(fdim1,lon)
                if add_fdim:self.fdim_txt+=temp_txt
                zi,temp_txt =get_level_index(fdim2,levs)
                if add_fdim:self.fdim_txt+=temp_txt

            if plot_type=='2D_lat_lev':
                ti,temp_txt =get_time_index(fdim1,Ls)
                if add_fdim:self.fdim_txt+=temp_txt
                loni,temp_txt =get_lon_index(fdim2,lon)
                if add_fdim:self.fdim_txt+=temp_txt

            if plot_type=='2D_lon_lev':
                ti,temp_txt =get_time_index(fdim1,Ls)
                if add_fdim:self.fdim_txt+=temp_txt
                lati,temp_txt =get_lat_index(fdim2,lat)
                if add_fdim:self.fdim_txt+=temp_txt


            if plot_type=='2D_time_lev':
                lati,temp_txt =get_lat_index(fdim1,lat)
                if add_fdim:self.fdim_txt+=temp_txt
                loni,temp_txt =get_lon_index(fdim2,lon)
                if add_fdim:self.fdim_txt+=temp_txt

            if plot_type=='2D_lon_time':
                lati,temp_txt =get_lat_index(fdim1,lat)
                if add_fdim:self.fdim_txt+=temp_txt
                zi,temp_txt =get_level_index(fdim2,levs)
                if add_fdim:self.fdim_txt+=temp_txt



            #If diurn, we will do the tod averaging first.
            if f_type=='diurn':
                var=f.variables[var_name][ti,todi,zi,lati,loni].reshape(len(np.atleast_1d(ti)),len(np.atleast_1d(todi)),\
                     len(np.atleast_1d(zi)),len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))
                var=np.nanmean(var,axis=1)
            else:
                var=f.variables[var_name][ti,zi,lati,loni].reshape(len(np.atleast_1d(ti)),\
                                                                len(np.atleast_1d(zi)),\
                                                                len(np.atleast_1d(lati)),\
                                                                len(np.atleast_1d(loni)))
            f.close()
            w=area_weights_deg(var.shape,lat[lati])


            #(u'time', u'pfull', u'lat', u'lon')
            if plot_type=='2D_lon_lat': return  lon,   lat,  np.nanmean(np.nanmean(var,axis=1),axis=0),var_info
            if plot_type=='2D_time_lat':return t_stack,lat,  np.nanmean(np.nanmean(var,axis=1),axis=2).T,var_info #transpose
            if plot_type=='2D_lat_lev':return  lat, levs,    np.nanmean(np.nanmean(var,axis=3),axis=0),var_info
            if plot_type=='2D_lon_lev':return  lon, levs,    np.nanmean(np.average(var,weights=w,axis=2),axis=0),var_info
            if plot_type=='2D_time_lev':return t_stack,levs, np.nanmean(np.average(var,weights=w,axis=2),axis=2).T,var_info #transpose
            if plot_type=='2D_lon_time':  return lon,t_stack,np.nanmean(np.average(var,weights=w,axis=2),axis=1),var_info



    def make_title(self,var_info,xlabel,ylabel):
        if self.title:
            plt.title(self.title,fontsize=label_size-self.nPan*label_factor)
        else:
            plt.title(var_info+'\n'+self.fdim_txt[1:],fontsize=label_size-self.nPan*label_factor) #we remove the first coma ',' of fdim_txt to print to the new line
        plt.xlabel(xlabel,fontsize=label_size-self.nPan*label_factor)
        plt.ylabel(ylabel,fontsize=label_size-self.nPan*label_factor)


    def make_colorbar(self,levs):
        if self.axis_opt2 =='log':
            formatter = LogFormatter(10, labelOnlyBase=False)
            if self.range:
                cbar=plt.colorbar(ticks=levs,orientation='horizontal',aspect=50,format=formatter)
            else:
                cbar=plt.colorbar(orientation='horizontal',aspect=50,format=formatter)

        else:
            cbar=plt.colorbar(orientation='horizontal',aspect=50)

        cbar.ax.tick_params(labelsize=label_size-self.nPan*label_factor) #shrink the colorbar label as the number of subplot increase

    def return_norm_levs(self):
        norm =None
        levs=None
        if self.axis_opt2 =='log':
            norm =LogNorm() # log mapping
        else: #default,linear mapping
            self.axis_opt2 ='lin'
            norm = None
        if self.range:
            if self.axis_opt2 =='lin':
                #Two numbers are provided, e.g. Cmin,Cmax
                if len(self.range)==2:
                    levs=np.linspace(self.range[0],self.range[1],levels)
                #The individual layers are provided
                else:
                    levs=self.range

            if self.axis_opt2 =='log':
                if self.range[0]<=0 or  self.range[1]<=0: prRed('*** Error using log scale, bounds cannot be zero or negative')
                levs=np.logspace(np.log10(self.range[0]),np.log10(self.range[1]),levels)
        return norm,levs

    def exception_handler(self,e,ax):
        if debug:raise
        sys.stdout.write("\033[F");sys.stdout.write("\033[K")#cursor up one line, then clear the whole line previous output
        prYellow('*** Warning *** %s'%(e))
        ax.text(0.5, 0.5, 'ERROR:'+str(e),horizontalalignment='center',verticalalignment='center', \
            bbox=dict(boxstyle="round",ec=(1., 0.5, 0.5),fc=(1., 0.8, 0.8),),\
            transform=ax.transAxes,wrap=True,fontsize=16)

    def fig_init(self):
        #create figure
        if self.layout is None : #No layout is specified
            out=fig_layout(self.subID,self.nPan,vertical_page)
        else:
            out=np.append(self.layout,self.subID)
        if self.subID==1:
            fig= plt.figure(facecolor='white',figsize=(width_inch, height_inch)) #create figure if 1st panel, 1.4 is ratio (16:9 screen would be 1.77)


        ax = plt.subplot(out[0],out[1],out[2]) #nrow,ncol,subID
        ax.patch.set_color('.1') #Nan are grey
        return ax

    def fig_save(self):
        #save the figure
        if  self.subID==self.nPan: #Last subplot
            if  self.subID==1: #1 plot
                if not '[' in self.varfull:
                    sensitive_name=self.varfull.split('{')[0].strip()  #add split '{' in case varfull contains layer, does not do anything otherwise
                    # varfull is a complex expression
                else:
                    sensitive_name='expression_'+get_list_varfull(self.varfull)[0].split('{')[0].strip()
            else: #multi panel
                sensitive_name='multi_panel'
            plt.tight_layout()
            self.fig_name=output_path+'/plots/'+sensitive_name+'.'+out_format
            self.fig_name=create_name(self.fig_name)
            plt.savefig(self.fig_name,dpi=my_dpi )
            if out_format!="pdf":print("Saved:" +self.fig_name)

    def filled_contour(self,xdata,ydata,var):
        cmap=self.axis_opt1
        #Personalized colormaps
        if cmap=='wbr':cmap=wbr_cmap()
        if cmap=='rjw':cmap=rjw_cmap()
        if cmap=='dkass_temp':cmap=dkass_temp_cmap()
        if cmap=='dkass_dust':cmap=dkass_dust_cmap()

        norm,levs=self.return_norm_levs()

        if self.range:
            plt.contourf(xdata, ydata,var,levs,extend='both',cmap=cmap,norm=norm)
        else:
            plt.contourf(xdata, ydata,var,levels,cmap=cmap,norm=norm)

        self.make_colorbar(levs)

    def solid_contour(self,xdata,ydata,var,contours):
       np.seterr(divide='ignore', invalid='ignore') #prevent error message when making contour
       if contours is None:
           CS=plt.contour(xdata, ydata,var,11,colors='k',linewidths=2)
       else:
           #If one contour is provided (as float), convert to array
           if type(contours)==float:contours=[contours]
           CS=plt.contour(xdata, ydata,var,contours,colors='k',linewidths=2)
       plt.clabel(CS, inline=1, fontsize=14,fmt='%g')


#===============================

class Fig_2D_lon_lat(Fig_2D):

    #make_template is calling method from the parent class
    def make_template(self):
        super(Fig_2D_lon_lat, self).make_template('Plot 2D lon X lat','Ls 0-360','Level Pa/m','lon','lat')

    def get_topo_2D(self,varfull,plot_type):

        '''
        This function returns the longitude, latitude and topography to overlay as contours in  2D_lon_lat plot
        Because the main variable requested may be complex, e.g. [00668.atmos_average_psdt2.temp]/1000., we will ensure to
        load the matching topography (here 00668.fixed.nc from the 2nd simulation), hence this function which does a simple task in a complicated way. Note that a great deal of the code is borrowed from the data_loader_2D() function

        Returns:
            zsurf: the topography or 'None' if no matching XXXXX.fixed.nc is found
        '''

        if not '[' in varfull:
            #---If overwriting dimensions, get the new dimensions and trim varfull from the '{lev=5.}' part
            if '{' in varfull :
                varfull,_,_,_=get_overwrite_dim_2D(varfull,plot_type,self.fdim1,self.fdim2,self.ftod)
            sol_array,filetype,var,simuID=split_varfull(varfull)
        #Realize a operation on the variables
        else:
            # Extract individual variables and prepare for execution
            varfull=remove_whitespace(varfull)
            varfull_list=get_list_varfull(varfull)
            f=get_list_varfull(varfull)
            sol_array,filetype,var,simuID=split_varfull(varfull_list[0])

        # If requesting a lat/lon plot for 00668.atmos_average.nc, try to find matching  00668.fixed.nc
        try:
            f, var_info,dim_info, dims=prep_file('zsurf','fixed',simuID,sol_array)
            #Get the file type ('fixed','diurn', 'average', 'daily') and interpolation type (pfull, zstd etc...)
            zsurf=f.variables['zsurf'][:,:]
            f.close()
        except:
            # If input file has not matching  00668.fixed.nc, return None
            zsurf=None
        return zsurf


    def do_plot(self):

        #create figure
        ax=super(Fig_2D_lon_lat, self).fig_init()
        try:    #try to do the figure, will return the error otherwise
            lon,lat,var,var_info=super(Fig_2D_lon_lat, self).data_loader_2D(self.varfull,self.plot_type)
            lon180,var=shift_data(lon,var)
            #Try to get topo if a matching XXXXX.fixed.nc file exist

            # Try to get topography is matching file
            try :
                surf=self.get_topo_2D(self.varfull,self.plot_type)
                _,zsurf=shift_data(lon,zsurf)
                add_topo=True
            except:
                add_topo=False


            projfull=self.axis_opt3
            #------------------------------------------------------------------------
            #If proj = cart, use the generic contours utility from the Fig_2D() class
            #------------------------------------------------------------------------
            if projfull=='cart':

                super(Fig_2D_lon_lat, self).filled_contour(lon180, lat,var)
                #---Add topo contour---
                if add_topo:plt.contour(lon180, lat,zsurf,11,colors='k',linewidths=0.5,linestyles='solid')   #topo

                if self.varfull2:
                    _,_,var2,var_info2=super(Fig_2D_lon_lat, self).data_loader_2D(self.varfull2,self.plot_type)
                    lon180,var2=shift_data(lon,var2)
                    super(Fig_2D_lon_lat, self).solid_contour(lon180, lat,var2,self.contour2)
                    var_info+=" (& "+var_info2+")"

                if self.Xlim:plt.xlim(self.Xlim[0],self.Xlim[1])
                if self.Ylim:plt.ylim(self.Ylim[0],self.Ylim[1])

                super(Fig_2D_lon_lat, self).make_title(var_info,'Longitude','Latitude')
             #--- Annotation---
                ax.xaxis.set_major_locator(MultipleLocator(30))
                ax.xaxis.set_minor_locator(MultipleLocator(10))
                ax.yaxis.set_major_locator(MultipleLocator(15))
                ax.yaxis.set_minor_locator(MultipleLocator(5))
                plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
                plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            #-------------------------------------------------------------------
            #                      Special projections
            #--------------------------------------------------------------------
            else:
                #Personalized colormaps
                cmap=self.axis_opt1
                if cmap=='wbr':cmap=wbr_cmap()
                if cmap=='rjw':cmap=rjw_cmap()
                norm,levs=super(Fig_2D_lon_lat, self).return_norm_levs()

                ax.axis('off')
                ax.patch.set_color('1') #Nan are reverse to white for projections
                if projfull[0:5] in ['Npole','Spole','ortho']:ax.set_aspect('equal')
                #---------------------------------------------------------------
                if projfull=='robin':
                    LON,LAT=np.meshgrid(lon180,lat)
                    X,Y=robin2cart(LAT,LON)

                    #Add meridans and parallel
                    for mer in np.arange(-180,180,30):
                        xg,yg=robin2cart(lat,lat*0+mer)
                        plt.plot(xg,yg,':k',lw=0.5)
                    #Label for 1 meridian out of 2:
                    for mer in np.arange(-180,181,90):
                        xl,yl=robin2cart(lat.min(),mer)
                        lab_txt=format_lon_lat(mer,'lon')
                        plt.text(xl,yl,lab_txt, fontsize=label_size-self.nPan*label_factor,verticalalignment='top',horizontalalignment='center')
                    for par in np.arange(-60,90,30):
                        xg,yg=robin2cart(lon180*0+par,lon180)
                        plt.plot(xg,yg,':k',lw=0.5)
                        xl,yl=robin2cart(par,180)
                        lab_txt=format_lon_lat(par,'lat')
                        plt.text(xl,yl,lab_txt, fontsize=label_size-self.nPan*label_factor)

                #---------------------------------------------------------------
                if projfull=='moll':
                    LON,LAT=np.meshgrid(lon180,lat)
                    X,Y=mollweide2cart(LAT,LON)
                    #Add meridans and parallel
                    for mer in np.arange(-180,180,30):
                        xg,yg=mollweide2cart(lat,lat*0+mer)
                        plt.plot(xg,yg,':k',lw=0.5)
                    #Label for 1 meridian out of 2:
                    for mer in [-180,0,180]:
                        xl,yl=mollweide2cart(lat.min(),mer)
                        lab_txt=format_lon_lat(mer,'lon')
                        plt.text(xl,yl,lab_txt, fontsize=label_size-self.nPan*label_factor,verticalalignment='top',horizontalalignment='center')

                    for par in np.arange(-60,90,30):
                        xg,yg=mollweide2cart(lon180*0+par,lon180)
                        xl,yl=mollweide2cart(par,180)
                        lab_txt=format_lon_lat(par,'lat')
                        plt.plot(xg,yg,':k',lw=0.5)
                        plt.text(xl,yl,lab_txt, fontsize=label_size-self.nPan*label_factor)

                if projfull[0:5] in ['Npole','Spole','ortho']:
                    #Common to all azimuthal projections
                    lon180_original=lon180.copy()
                    var,lon180=add_cyclic(var,lon180)
                    if add_topo:zsurf,_=add_cyclic(zsurf,lon180_original)
                    lon_lat_custom=None #Initialization
                    lat_b=None

                    #Get custom lat/lon, if any
                    if len(projfull)>5:lon_lat_custom=filter_input(projfull[5:],'float')

                if projfull[0:5]=='Npole':
                    #Reduce data
                    lat_b=60
                    if not(lon_lat_custom is None):lat_b=lon_lat_custom #bounding lat
                    lat_bi,_=get_lat_index(lat_b,lat)
                    lat=lat[lat_bi:]
                    var=var[lat_bi:,:]
                    if add_topo:zsurf=zsurf[lat_bi:,:]
                    LON,LAT=np.meshgrid(lon180,lat)
                    X,Y=azimuth2cart(LAT,LON,90,0)

                     #Add meridans and parallel
                    for mer in np.arange(-180,180,30):
                        xg,yg=azimuth2cart(lat,lat*0+mer,90)
                        plt.plot(xg,yg,':k',lw=0.5)
                    for mer in np.arange(-150,180,30):     #skip 190W to leave room for title
                        xl,yl=azimuth2cart(lat.min()-3,mer,90) #Put label 3 degree south of the bounding latitude
                        lab_txt=format_lon_lat(mer,'lon')
                        plt.text(xl,yl,lab_txt, fontsize=label_size-self.nPan*label_factor,verticalalignment='top',horizontalalignment='center')
                    #Parallels start from 80N, every 10 degree
                    for par in  np.arange(80,lat.min(),-10):
                        xg,yg=azimuth2cart(lon180*0+par,lon180,90)
                        plt.plot(xg,yg,':k',lw=0.5)
                        xl,yl=azimuth2cart(par,180,90)
                        lab_txt=format_lon_lat(par,'lat')
                        plt.text(xl,yl,lab_txt, fontsize=5)
                if projfull[0:5]=='Spole':
                    lat_b=-60
                    if not(lon_lat_custom is None):lat_b=lon_lat_custom #bounding lat
                    lat_bi,_=get_lat_index(lat_b,lat)
                    lat=lat[:lat_bi]
                    var=var[:lat_bi,:]
                    if add_topo:zsurf=zsurf[:lat_bi,:]
                    LON,LAT=np.meshgrid(lon180,lat)
                    X,Y=azimuth2cart(LAT,LON,-90,0)
                    #Add meridans and parallel
                    for mer in np.arange(-180,180,30):
                        xg,yg=azimuth2cart(lat,lat*0+mer,-90)
                        plt.plot(xg,yg,':k',lw=0.5)
                    for mer in np.append(np.arange(-180,0,30),np.arange(30,180,30)):    #skip zero to leave room for title
                        xl,yl=azimuth2cart(lat.max()+3,mer,-90) #Put label 3 degree north of the bounding latitude
                        lab_txt=format_lon_lat(mer,'lon')
                        plt.text(xl,yl,lab_txt, fontsize=label_size-self.nPan*label_factor,verticalalignment='top',horizontalalignment='center')
                    #Parallels start from 80S, every 10 degree
                    for par in np.arange(-80,lat.max(),10):
                        xg,yg=azimuth2cart(lon180*0+par,lon180,-90)
                        plt.plot(xg,yg,':k',lw=0.5)
                        xl,yl=azimuth2cart(par,180,-90)
                        lab_txt=format_lon_lat(par,'lat')
                        plt.text(xl,yl,lab_txt, fontsize=5)

                if projfull[0:5]=='ortho':
                    #Initialization
                    lon_p,lat_p=-120,20
                    if not(lon_lat_custom is None):lon_p=lon_lat_custom[0];lat_p=lon_lat_custom[1] #bounding lat
                    LON,LAT=np.meshgrid(lon180,lat)
                    X,Y,MASK=ortho2cart(LAT,LON,lat_p,lon_p)
                    #Mask opposite side of the planet
                    var=var*MASK
                    if add_topo:zsurf=zsurf*MASK
                     #Add meridans and parallel
                    for mer in np.arange(-180,180,30):
                        xg,yg,maskg=ortho2cart(lat,lat*0+mer,lat_p,lon_p)
                        plt.plot(xg*maskg,yg,':k',lw=0.5)
                    for par in np.arange(-60,90,30):
                        xg,yg,maskg=ortho2cart(lon180*0+par,lon180,lat_p,lon_p)
                        plt.plot(xg*maskg,yg,':k',lw=0.5)


                if self.range:
                    plt.contourf(X, Y,var,levs,extend='both',cmap=cmap,norm=norm)
                else:
                    plt.contourf(X, Y,var,levels,cmap=cmap,norm=norm)

                super(Fig_2D_lon_lat, self).make_colorbar(levs)


                #---Add topo contour---
                if add_topo:plt.contour(X, Y ,zsurf,11,colors='k',linewidths=0.5,linestyles='solid')   #topo
                #=================================================================================
                #=======================Solid contour 2nd variables===============================
                #=================================================================================
                if self.varfull2:
                    lon,lat,var2,var_info2=super(Fig_2D_lon_lat, self).data_loader_2D(self.varfull2,self.plot_type)
                    lon180,var2=shift_data(lon,var2)

                    if projfull=='robin':
                        LON,LAT=np.meshgrid(lon180,lat)
                        X,Y=robin2cart(LAT,LON)

                    if projfull=='moll':
                        LON,LAT=np.meshgrid(lon180,lat)
                        X,Y=mollweide2cart(LAT,LON)

                    if projfull[0:5] in ['Npole','Spole','ortho']:
                        #Common to all azimutal projections
                        var2,lon180=add_cyclic(var2,lon180)
                        lon_lat_custom=None #Initialization
                        lat_b=None

                        #Get custom lat/lon, if any
                        if len(projfull)>5:lon_lat_custom=filter_input(projfull[5:],'float')

                    if projfull[0:5]=='Npole':
                        #Reduce data
                        lat_b=60
                        if not(lon_lat_custom is None):lat_b=lon_lat_custom #bounding lat
                        lat_bi,_=get_lat_index(lat_b,lat)
                        lat=lat[lat_bi:]
                        var2=var2[lat_bi:,:]
                        LON,LAT=np.meshgrid(lon180,lat)
                        X,Y=azimuth2cart(LAT,LON,90,0)
                    if projfull[0:5]=='Spole':
                        lat_b=-60
                        if not(lon_lat_custom is None):lat_b=lon_lat_custom #bounding lat
                        lat_bi,_=get_lat_index(lat_b,lat)
                        lat=lat[:lat_bi]
                        var2=var2[:lat_bi,:]
                        LON,LAT=np.meshgrid(lon180,lat)
                        X,Y=azimuth2cart(LAT,LON,-90,0)

                    if projfull[0:5]=='ortho':
                        #Initialization
                        lon_p,lat_p=-120,20
                        if not(lon_lat_custom is None):lon_p=lon_lat_custom[0];lat_p=lon_lat_custom[1] #bounding lat
                        LON,LAT=np.meshgrid(lon180,lat)
                        X,Y,MASK=ortho2cart(LAT,LON,lat_p,lon_p)
                        #Mask opposite side of the planet
                        var2=var2*MASK

                    np.seterr(divide='ignore', invalid='ignore') #prevent error message when making contour
                    if self.contour2 is None:
                        CS=plt.contour(X, Y,var2,11,colors='k',linewidths=2)
                    else:
                        #If one contour is provided (as float), convert to array
                        if type(self.contour2)==float:self.contour2=[self.contour2]
                        CS=plt.contour(X, Y,var2,self.contour2,colors='k',linewidths=2)
                    plt.clabel(CS, inline=1, fontsize=14,fmt='%g')

                    var_info+=" (& "+var_info2+")"


                if self.title:
                    plt.title(self.title,fontsize=label_size-self.nPan*label_factor)
                else:
                    plt.title(var_info+'\n'+self.fdim_txt[1:],fontsize=label_size-self.nPan*label_factor) #we remove the first coma ',' of fdim_txt to print to the new line


            self.success=True

        except Exception as e: #Return the error
            super(Fig_2D_lon_lat, self).exception_handler(e,ax)
        super(Fig_2D_lon_lat, self).fig_save()

class Fig_2D_time_lat(Fig_2D):

    def make_template(self):
        #make_template is calling method from the parent class
        super(Fig_2D_time_lat, self).make_template('Plot 2D time X lat','Lon +/-180','Level [Pa/m]','Ls','lat')
                                                                        #self.fdim1,  self.fdim2, self.Xlim,self.Ylim

    def do_plot(self):
        #create figure
        ax=super(Fig_2D_time_lat, self).fig_init()
        try:    #try to do the figure, will return the error otherwise

            t_stack,lat,var,var_info=super(Fig_2D_time_lat, self).data_loader_2D(self.varfull,self.plot_type)
            tim=t_stack[0,:];Ls=t_stack[1,:]

            super(Fig_2D_time_lat, self).filled_contour(Ls, lat,var)

            if self.varfull2:
                _,_,var2,var_info2=super(Fig_2D_time_lat, self).data_loader_2D(self.varfull2,self.plot_type)
                super(Fig_2D_time_lat, self).solid_contour(Ls, lat,var2,self.contour2)
                var_info+=" (& "+var_info2+")"


            #Axis formatting
            if self.Xlim:
                idmin=np.argmin(np.abs(tim-self.Xlim[0]))
                idmax=np.argmin(np.abs(tim-self.Xlim[1]))
                plt.xlim([Ls[idmin],Ls[idmax]])

            if self.Ylim:plt.ylim(self.Ylim[0],self.Ylim[1])

            Ls_ticks = [item for item in ax.get_xticks()]
            labels = [item for item in ax.get_xticklabels()]


            for i in range(0,len(Ls_ticks)):
                id=np.argmin(np.abs(Ls-Ls_ticks[i])) #find tmstep closest to this tick
                labels[i]='Ls %g\nsol %i'%(np.mod(Ls_ticks[i],360.),tim[id])


            ax.set_xticklabels(labels)

            super(Fig_2D_time_lat, self).make_title(var_info,'','Latitude') #no 'Time' label as it is obvious

            ax.yaxis.set_major_locator(MultipleLocator(15))
            ax.yaxis.set_minor_locator(MultipleLocator(5))
            plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)

            self.success=True

        except Exception as e: #Return the error
            super(Fig_2D_time_lat, self).exception_handler(e,ax)
        super(Fig_2D_time_lat, self).fig_save()

class Fig_2D_lat_lev(Fig_2D):

    def make_template(self):
        #make_template is calling method from the parent class
        super(Fig_2D_lat_lev, self).make_template('Plot 2D lat X lev','Ls 0-360 ','Lon +/-180','Lat','level[Pa/m]')
                                                                          #self.fdim1,  self.fdim2, self.Xlim,self.Ylim
    def do_plot(self):
        #create figure
        ax=super(Fig_2D_lat_lev, self).fig_init()
        try:    #try to do the figure, will return the error otherwise

            lat,pfull,var,var_info=super(Fig_2D_lat_lev, self).data_loader_2D(self.varfull,self.plot_type)
            super(Fig_2D_lat_lev, self).filled_contour(lat,pfull,var)

            if self.varfull2:
                _,_,var2,var_info2=super(Fig_2D_lat_lev, self).data_loader_2D(self.varfull2,self.plot_type)
                super(Fig_2D_lat_lev, self).solid_contour(lat, pfull,var2,self.contour2)
                var_info+=" (& "+var_info2+")"

            if self.vert_unit=='Pa':
                ax.set_yscale("log")
                ax.invert_yaxis()
                ylabel_txt='Pressure [Pa]'
            else:
                ylabel_txt='Altitude [m]'


            if self.Xlim:plt.xlim(self.Xlim)
            if self.Ylim:plt.ylim(self.Ylim)

            super(Fig_2D_lat_lev, self).make_title(var_info,'Latitude',ylabel_txt)


            ax.xaxis.set_major_locator(MultipleLocator(15))
            ax.xaxis.set_minor_locator(MultipleLocator(5))
            plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)


            self.success=True
        except Exception as e: #Return the error
            super(Fig_2D_lat_lev, self).exception_handler(e,ax)
        super(Fig_2D_lat_lev, self).fig_save()

class Fig_2D_lon_lev(Fig_2D):

    def make_template(self):
        #make_template is calling method from the parent class
        super(Fig_2D_lon_lev, self).make_template('Plot 2D lon X lev','Ls 0-360 ','Latitude','Lon +/-180','level[Pa/m]')

    def do_plot(self):
        #create figure
        ax=super(Fig_2D_lon_lev, self).fig_init()
        try:    #try to do the figure, will return the error otherwise

            lon,pfull,var,var_info=super(Fig_2D_lon_lev, self).data_loader_2D(self.varfull,self.plot_type)
            lon180,var=shift_data(lon,var)

            super(Fig_2D_lon_lev, self).filled_contour(lon180,pfull,var)

            if self.varfull2:
                _,_,var2,var_info2=super(Fig_2D_lon_lev, self).data_loader_2D(self.varfull2,self.plot_type)
                _,var2=shift_data(lon,var2)
                super(Fig_2D_lon_lev, self).solid_contour(lon180, pfull,var2,self.contour2)
                var_info+=" (& "+var_info2+")"


            if self.vert_unit=='Pa':
                ax.set_yscale("log")
                ax.invert_yaxis()
                ylabel_txt='Pressure [Pa]'
            else:
                ylabel_txt='Altitude [m]'

            if self.Xlim:plt.xlim(self.Xlim)
            if self.Ylim:plt.ylim(self.Ylim)

            super(Fig_2D_lon_lev, self).make_title(var_info,'Longitude',ylabel_txt)

            ax.xaxis.set_major_locator(MultipleLocator(30))
            ax.xaxis.set_minor_locator(MultipleLocator(10))
            plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)

            self.success=True
        except Exception as e: #Return the error
            super(Fig_2D_lon_lev, self).exception_handler(e,ax)
        super(Fig_2D_lon_lev, self).fig_save()

class Fig_2D_time_lev(Fig_2D):

    def make_template(self):
        #make_template is calling method from the parent class
        super(Fig_2D_time_lev, self).make_template('Plot 2D time X lev','Latitude','Lon +/-180','Ls','level[Pa/m]')

    def do_plot(self):
        #create figure
        ax=super(Fig_2D_time_lev, self).fig_init()
        try:    #try to do the figure, will return the error otherwise

            t_stack,pfull,var,var_info=super(Fig_2D_time_lev, self).data_loader_2D(self.varfull,self.plot_type)
            tim=t_stack[0,:];Ls=t_stack[1,:]
            super(Fig_2D_time_lev, self).filled_contour(Ls,pfull,var)

            if self.varfull2:
                _,_,var2,var_info2=super(Fig_2D_time_lev, self).data_loader_2D(self.varfull2,self.plot_type)
                super(Fig_2D_time_lev, self).solid_contour(Ls, pfull,var2,self.contour2)
                var_info+=" (& "+var_info2+")"


            #Axis formatting
            if self.Xlim:
                idmin=np.argmin(np.abs(tim-self.Xlim[0]))
                idmax=np.argmin(np.abs(tim-self.Xlim[1]))
                plt.xlim([Ls[idmin],Ls[idmax]])
            if self.Ylim:plt.ylim(self.Ylim)

            Ls_ticks = [item for item in ax.get_xticks()]
            labels = [item for item in ax.get_xticklabels()]


            for i in range(0,len(Ls_ticks)):
                id=np.argmin(np.abs(Ls-Ls_ticks[i])) #find tmstep closest to this tick
                labels[i]='Ls %g\nsol %i'%(np.mod(Ls_ticks[i],360.),tim[id])


            ax.set_xticklabels(labels)
            plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)

            if self.vert_unit=='Pa':
                ax.set_yscale("log")
                ax.invert_yaxis()
                ylabel_txt='Pressure [Pa]'
            else:
                ylabel_txt='Altitude [m]'

            super(Fig_2D_time_lev, self).make_title(var_info,'',ylabel_txt)

            self.success=True
        except Exception as e: #Return the error
            super(Fig_2D_time_lev, self).exception_handler(e,ax)
        super(Fig_2D_time_lev, self).fig_save()

class Fig_2D_lon_time(Fig_2D):

    def make_template(self):
        #make_template is calling method from the parent class
        super(Fig_2D_lon_time, self).make_template('Plot 2D lon X time','Latitude','Level [Pa/m]','Lon +/-180','Ls')

    def do_plot(self):
        #create figure
        ax=super(Fig_2D_lon_time, self).fig_init()
        try:    #try to do the figure, will return the error otherwise

            lon,t_stack,var,var_info=super(Fig_2D_lon_time, self).data_loader_2D(self.varfull,self.plot_type)
            lon180,var=shift_data(lon,var)
            tim=t_stack[0,:];Ls=t_stack[1,:]
            super(Fig_2D_lon_time, self).filled_contour(lon180,Ls,var)

            if self.varfull2:
                _,_,var2,var_info2=super(Fig_2D_lon_time, self).data_loader_2D(self.varfull2,self.plot_type)
                _,var2=shift_data(lon,var2)
                super(Fig_2D_lon_time, self).solid_contour(lon180,Ls,var2,self.contour2)
                var_info+=" (& "+var_info2+")"


            #Axis formatting
            if self.Xlim:plt.xlim(self.Xlim)
            #Axis formatting
            if self.Ylim:
                idmin=np.argmin(np.abs(tim-self.Ylim[0]))
                idmax=np.argmin(np.abs(tim-self.Ylim[1]))
                plt.ylim([Ls[idmin],Ls[idmax]])


            Ls_ticks = [item for item in ax.get_yticks()]
            labels = [item for item in ax.get_yticklabels()]


            for i in range(0,len(Ls_ticks)):
                id=np.argmin(np.abs(Ls-Ls_ticks[i])) #find tmstep closest to this tick
                labels[i]='Ls %g\nsol %i'%(np.mod(Ls_ticks[i],360.),tim[id])

            ax.set_yticklabels(labels)

            ax.xaxis.set_major_locator(MultipleLocator(30))
            ax.xaxis.set_minor_locator(MultipleLocator(10))

            super(Fig_2D_lon_time, self).make_title(var_info,'Longitude','')
            plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)

            self.success=True
        except Exception as e: #Return the error
            super(Fig_2D_lon_time, self).exception_handler(e,ax)
        super(Fig_2D_lon_time, self).fig_save()

class Fig_1D(object):
    # Parent class for 1D figures
    def __init__(self,varfull='atmos_average.ts',doPlot=True):

        self.legend=None
        self.varfull=varfull
        self.t='AXIS' #default value for AXIS
        self.lat=None
        self.lon=None
        self.lev=None
        self.ftod=None  #Time of day, requested input
        self.hour=None  #Time of , boolean for diurnal plots only.
        # Logic
        self.doPlot=doPlot
        self.plot_type='1D_time'

        #Extract filetype, variable, and simulation ID (initialization only)
        self.sol_array,self.filetype,self.var,self.simuID=split_varfull(self.varfull)

        #Multi panel
        self.nPan=1
        self.subID=1
        self.addLine=False
        self.layout = None # e.g. [2,3], used only if 'HOLD ON 2,3' is used
        #Annotation for free dimensions
        self.fdim_txt=''
        self.success=False
        self.vert_unit='' #m or Pa
        #Axis options

        self.Dlim=None #Dimension limit
        self.Vlim=None #variable limits
        self.axis_opt1='-'



    def make_template(self):
        customFileIN.write("<<<<<<<<<<<<<<| Plot 1D = {0} |>>>>>>>>>>>>>\n".format(self.doPlot))
        customFileIN.write("Legend         = %s\n"%(self.legend))             #1
        customFileIN.write("Main Variable  = %s\n"%(self.varfull))            #2
        customFileIN.write("Ls 0-360       = {0}\n".format(self.t))           #3
        customFileIN.write("Latitude       = {0}\n".format(self.lat))         #4
        customFileIN.write("Lon +/-180     = {0}\n".format(self.lon))         #5
        customFileIN.write("Level [Pa/m]   = {0}\n".format(self.lev))         #6
        customFileIN.write("Diurnal  [hr]  = {0}\n".format(self.hour))        #7
        customFileIN.write("Axis Options  : lat,lon+/-180,[Pa/m],Ls = [None,None] | var = [None,None] | linestyle = - | axlabel = None \n")#7

    def read_template(self):
        self.legend= rT('char')             #1
        self.varfull=rT('char')             #2
        self.t=rT('float')                  #3
        self.lat=rT('float')                #4
        self.lon=rT('float')                #5
        self.lev=rT('float')                #6
        self.hour=rT('float')               #7
        self.Dlim,self.Vlim,self.axis_opt1,self.axis_opt2,_=read_axis_options(customFileIN.readline())     #7

        self.plot_type=self.get_plot_type()


    def get_plot_type(self):
        '''
        Note that the or self.t =='AXIS' test  and the  self.t  =-88888 assignment are only used when MarsPlot is used without a template
        '''
        ncheck=0
        graph_type='Error'
        if self.t  ==-88888 or self.t    =='AXIS': self.t  =-88888;graph_type='1D_time';ncheck+=1
        if self.lat==-88888 or self.lat  =='AXIS': self.lat=-88888;graph_type='1D_lat' ;ncheck+=1
        if self.lon==-88888 or self.lon  =='AXIS': self.lon=-88888;graph_type='1D_lon' ;ncheck+=1
        if self.lev==-88888 or self.lev  =='AXIS': self.lev=-88888;graph_type='1D_lev' ;ncheck+=1
        if self.hour==-88888 or self.hour =='AXIS': self.hour=-88888;graph_type='1D_diurn';ncheck+=1
        if ncheck==0:
            prYellow('''*** Warning *** In 1D plot, %s: use 'AXIS' to set varying dimension '''%(self.varfull))
        if ncheck>1:
            prYellow('''*** Warning *** In 1D plot, %s: 'AXIS' keyword may only be used once '''%(self.varfull))
        return graph_type


    def data_loader_1D(self,varfull,plot_type):

        if not '[' in varfull:
            if '{' in varfull :
                varfull,t_req,lat_req,lon_req,lev_req,ftod_req=get_overwrite_dim_1D(varfull,self.t,self.lat,self.lon,self.lev,self.ftod)
                # t_req,lat_req,lon_req,lev_req constain the dimensions to overwrite is '{}' are provided of the default self.t,self.lat,self.lon,self.lev otherwise
            else: # no '{ }' use to overwrite the dimensions, copy the plots' defaults
                t_req,lat_req,lon_req,lev_req,ftod_req= self.t,self.lat,self.lon,self.lev,self.ftod
            sol_array,filetype,var,simuID=split_varfull(varfull)
            xdata,var,var_info=self.read_NCDF_1D(var,filetype,simuID,sol_array,plot_type,t_req,lat_req,lon_req,lev_req,ftod_req)

        else:
            VAR=[]
            # Extract individual variables and prepare for execution
            varfull=remove_whitespace(varfull)
            varfull_list=get_list_varfull(varfull)
            expression_exec=create_exec(varfull,varfull_list)

            #Initialize list of requested dimensions;
            t_list=[None]*len(varfull_list)
            lat_list=[None]*len(varfull_list)
            lon_list=[None]*len(varfull_list)
            lev_list=[None]*len(varfull_list)
            ftod_list=[None]*len(varfull_list)
            expression_exec=create_exec(varfull,varfull_list)

            for i in range(0,len(varfull_list)):
                #---If overwriting dimensions, get the new dimensions and trim varfull from the '{lev=5.}' part
                if '{' in varfull_list[i] :
                    varfull_list[i],t_list[i],lat_list[i],lon_list[i],lev_list[i],ftod_list[i]=get_overwrite_dim_1D(varfull_list[i],self.t,self.lat,self.lon,self.lev,self.ftod)
                else: # no '{ }' use to overwrite the dimensions, copy the plots' defaults
                    t_list[i],lat_list[i],lon_list[i],lev_list[i],ftod_list[i]=self.t,self.lat,self.lon,self.lev,self.ftod
                sol_array,filetype,var,simuID=split_varfull(varfull_list[i])
                xdata,temp,var_info=self.read_NCDF_1D(var,filetype,simuID,sol_array,plot_type,t_list[i],lat_list[i],lon_list[i],lev_list[i],ftod_list[i])
                VAR.append(temp)
            var_info=varfull
            var=eval(expression_exec)

        return xdata,var,var_info

    def read_NCDF_1D(self,var_name,file_type,simuID,sol_array,plot_type,t_req,lat_req,lon_req,lev_req,ftod_req):
        '''
        Given an expression object with '[]' return the different variable needed
        Args:
            var_name: variable name, e.g 'temp'
            file_type: 'fixed' or 'atmos_average'
            sol_array: sol if different from default e.g '02400'
            plot_type: '1D-time','1D_lon', '1D_lat', '1D_lev' and '1D_time'
            t_req,lat_req,lon_req,lev_req,ftod_req: the Ls, lat, lon, level [Pa/m] and time of day requested
        Returns:
            dim_array: the axis, e.g one array of longitudes
            var_array: the variable extracted

        '''

        f, var_info,dim_info, dims=prep_file(var_name,file_type,simuID,sol_array)


        #Get the file type ('fixed','diurn', 'average', 'daily') and interpolation type (pfull, zstd etc...)
        f_type,interp_type=FV3_file_type(f)

        #If self.fdim is empty, add the variable (do only once)
        add_fdim=False
        if not self.fdim_txt.strip():add_fdim=True

        #Initialize dimensions (These are in all the .nc files)

        lat=f.variables['lat'][:];lati=np.arange(0,len(lat))
        lon=f.variables['lon'][:];loni=np.arange(0,len(lon))



        #------------------------Time of Day ----------------------------
        # For diurn files, we will select data on the time-of-day axis and update dimensions
        # so the resulting variable is the same as atmos_average and atmos_daily file.
        # This simplifies the logic a bit so all atmos_daily, atmos_average and atmos_diurn are treated the same when
        # the request is 1D-time, 1D_lon, 1D_lat, and 1D_lev. Naturally the plot type '1D_diurn' will be an exeception so the following
        # lines should be skipped if that is the case.

        # Time of day is always the 2nd dimension, i.e. dim_info[1]

        #Note: This step is performed only if the file is of type 'atmos_diurn', and the requested the plot  is 1D_lat, 1D_lev or 1D_time
        if (f_type=='diurn' and dim_info[1][:11]=='time_of_day') and not plot_type=='1D_diurn':
            tod=f.variables[dim_info[1]][:]
            todi,temp_txt =get_tod_index(ftod_req,tod)
            # Update dim_info from ('time','time_of_day_XX, 'lat', 'lon') to  ('time', 'lat', 'lon')
            # OR ('time','time_of_day_XX, 'pfull','lat', 'lon') to  ('time', 'pfull','lat', 'lon') etc...
            dim_info=(dim_info[0],)+dim_info[2:]
            if add_fdim:self.fdim_txt+=temp_txt



        #======static======= , ignore level and time dimension
        if dim_info==(u'lat', u'lon'):
            if plot_type=='1D_lat':
                loni,temp_txt =get_lon_index(lon_req,lon)
            elif plot_type=='1D_lon':
                lati,temp_txt =get_lat_index(lat_req,lat)

            if add_fdim:self.fdim_txt+=temp_txt
            var=f.variables[var_name][lati,loni].reshape(len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))
            f.close()
            w=area_weights_deg(var.shape,lat[lati])

            if plot_type=='1D_lat': return  lat, np.nanmean(var,axis=1),var_info
            if plot_type=='1D_lon': return  lon, np.average(var,weights=w,axis=0),var_info

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #~~~~This section is for 1D_time, 1D_lat, 1D_lon and 1D_lev only~~~~
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if not plot_type=='1D_diurn':
            #======time,lat,lon=======
            if dim_info==(u'time', u'lat', u'lon'):

            #Initialize dimension
                t=f.variables['time'][:];Ls=np.squeeze(f.variables['areo'][:]);ti=np.arange(0,len(t))
                #For diurn file, change time_of_day(time,24,1) to time_of_day(time) at midnight UT
                if f_type=='diurn'and len(Ls.shape)>1:Ls=np.squeeze(Ls[:,0])
                t_stack=np.vstack((t,Ls)) #stack the time and ls array as one variable

                if plot_type=='1D_lat':
                    ti,temp_txt =get_time_index(t_req,Ls)
                    if add_fdim:self.fdim_txt+=temp_txt
                    loni,temp_txt =get_lon_index(lon_req,lon)
                    if add_fdim:self.fdim_txt+=temp_txt
                if plot_type=='1D_lon':
                    lati,temp_txt =get_lat_index(lat_req,lat)
                    if add_fdim:self.fdim_txt+=temp_txt
                    ti,temp_txt =get_time_index(t_req,Ls)
                    if add_fdim:self.fdim_txt+=temp_txt
                if plot_type=='1D_time':
                    loni,temp_txt =get_lon_index(lon_req,lon)
                    if add_fdim:self.fdim_txt+=temp_txt
                    lati,temp_txt =get_lat_index(lat_req,lat)
                    if add_fdim:self.fdim_txt+=temp_txt


                if f_type=='diurn':
                    var=f.variables[var_name][ti,todi,lati,loni].reshape(len(np.atleast_1d(ti)),len(np.atleast_1d(todi)),\
                        len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))
                    var=np.nanmean(var,axis=1)
                else:
                    var=f.variables[var_name][ti,lati,loni].reshape(len(np.atleast_1d(ti)),len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))

                f.close()

                w=area_weights_deg(var.shape,lat[lati])


                #Return data
                if plot_type=='1D_lat': return lat,    np.nanmean(np.nanmean(var,axis=2),axis=0),var_info
                if plot_type=='1D_lon': return lon,    np.nanmean(np.average(var,weights=w,axis=1),axis=0),var_info
                if plot_type=='1D_time':return t_stack,np.nanmean(np.average(var,weights=w,axis=1),axis=1),var_info


            #======time,level,lat,lon=======
            if   (dim_info==(u'time', u'pfull', u'lat', u'lon')
            or dim_info==(u'time', u'level', u'lat', u'lon')
            or dim_info==(u'time', u'pstd', u'lat', u'lon')
            or dim_info==(u'time', u'zstd', u'lat', u'lon')
            or dim_info==(u'time', u'zagl', u'lat', u'lon')
            or dim_info==(u'time', u'zgrid', u'lat', u'lon')):

                if dim_info[1] in ['pfull','level','pstd']:  self.vert_unit='Pa'
                if dim_info[1] in ['zagl','zstd']:  self.vert_unit='m'

                #Initialize dimensions
                levs=f.variables[dim_info[1]][:]
                zi=np.arange(0,len(levs))
                t=f.variables['time'][:];Ls=np.squeeze(f.variables['areo'][:]);ti=np.arange(0,len(t))
                #For diurn file, change time_of_day(time,24,1) to time_of_day(time) at midnight UT
                if f_type=='diurn'and len(Ls.shape)>1:Ls=np.squeeze(Ls[:,0])
                t_stack=np.vstack((t,Ls)) #stack the time and ls array as one variable

                if plot_type=='1D_lat':
                    ti,temp_txt =get_time_index(t_req,Ls)
                    if add_fdim:self.fdim_txt+=temp_txt
                    loni,temp_txt =get_lon_index(lon_req,lon)
                    if add_fdim:self.fdim_txt+=temp_txt
                    zi,temp_txt =get_level_index(lev_req,levs)
                    if add_fdim:self.fdim_txt+=temp_txt

                if plot_type=='1D_lon':
                    lati,temp_txt =get_lat_index(lat_req,lat)
                    if add_fdim:self.fdim_txt+=temp_txt
                    ti,temp_txt =get_time_index(t_req,Ls)
                    if add_fdim:self.fdim_txt+=temp_txt
                    zi,temp_txt =get_level_index(lev_req,levs)
                    if add_fdim:self.fdim_txt+=temp_txt

                if plot_type=='1D_time':
                    loni,temp_txt =get_lon_index(lon_req,lon)
                    if add_fdim:self.fdim_txt+=temp_txt
                    lati,temp_txt =get_lat_index(lat_req,lat)
                    if add_fdim:self.fdim_txt+=temp_txt
                    zi,temp_txt =get_level_index(lev_req,levs)
                    if add_fdim:self.fdim_txt+=temp_txt

                if plot_type=='1D_lev':
                    ti,temp_txt =get_time_index(t_req,Ls)
                    if add_fdim:self.fdim_txt+=temp_txt
                    lati,temp_txt =get_lat_index(lat_req,lat)
                    if add_fdim:self.fdim_txt+=temp_txt
                    loni,temp_txt =get_lon_index(lon_req,lon)
                    if add_fdim:self.fdim_txt+=temp_txt

                #Fix for new netcdf4 version: get array elements instead of manipulation the variable
                # It used to be var= f.variables[var_name]


                #If diurn, we will do the tod averaging first.
                if f_type=='diurn':
                    var=f.variables[var_name][ti,todi,zi,lati,loni].reshape(len(np.atleast_1d(ti)),len(np.atleast_1d(todi)),\
                        len(np.atleast_1d(zi)),len(np.atleast_1d(lati)),len(np.atleast_1d(loni)))
                    var=np.nanmean(var,axis=1)
                else:
                    reshape_shape=[len(np.atleast_1d(ti)),\
                                                                    len(np.atleast_1d(zi)),\
                                                                    len(np.atleast_1d(lati)),\
                                                                    len(np.atleast_1d(loni))]
                    var=f.variables[var_name][ti,zi,lati,loni].reshape(reshape_shape)
                f.close()

                w=area_weights_deg(var.shape,lat[lati])


                #(u'time', u'pfull', u'lat', u'lon')
                if plot_type=='1D_lat': return lat,    np.nanmean(np.nanmean(np.nanmean(var,axis=3),axis=1),axis=0),var_info
                if plot_type=='1D_lon': return lon,    np.nanmean(np.nanmean(np.average(var,weights=w,axis=2),axis=1),axis=0),var_info
                if plot_type=='1D_time':return t_stack,np.nanmean(np.nanmean(np.average(var,weights=w,axis=2),axis=2),axis=1),var_info
                if plot_type=='1D_lev': return levs,   np.nanmean(np.nanmean(np.average(var,weights=w,axis=2),axis=2),axis=0),var_info

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #~~~~~~~~~~~~~This section is for 1D_diurn, only~~~~~~~~~~~~~~~~~~~~
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        else:
            #Find name of tod variable, it could be 'time_of_day_16', or 'time_of_day_24'
            tod_dim_name=find_tod_in_diurn(f)
            tod=f.variables[tod_dim_name][:]
            todi=np.arange(0,len(tod))


            #======time,lat,lon=======
            if f.variables[var_name].dimensions==('time',tod_dim_name ,'lat', 'lon'):

            #Initialize dimension
                t=f.variables['time'][:];Ls=np.squeeze(f.variables['areo'][:]);ti=np.arange(0,len(t))
                #For diurn file, change time_of_day(time,24,1) to time_of_day(time) at midnight UT
                if f_type=='diurn'and len(Ls.shape)>1:Ls=np.squeeze(Ls[:,0])
                t_stack=np.vstack((t,Ls)) #stack the time and ls array as one variable

                loni,temp_txt =get_lon_index(lon_req,lon)
                if add_fdim:self.fdim_txt+=temp_txt
                lati,temp_txt =get_lat_index(lat_req,lat)
                if add_fdim:self.fdim_txt+=temp_txt
                ti,temp_txt =get_time_index(t_req,Ls)
                if add_fdim:self.fdim_txt+=temp_txt

                reshape_shape=[len(np.atleast_1d(ti)),len(np.atleast_1d(tod)),\
                        len(np.atleast_1d(lati)),len(np.atleast_1d(loni))]

                #Broadcast dimensions before extraction. This is a 'new' requirement for numpy
                var=f.variables[var_name][ti,:,lati,loni].reshape(reshape_shape)
                f.close()

                w=area_weights_deg(var.shape,lat[lati])
                #Return data
                #('time','time_of_day','lat', u'lon')
                return tod, np.nanmean(np.nanmean(np.average(var,weights=w,axis=2),axis=2),axis=0),var_info



            #======time,level,lat,lon=======
            if   (dim_info==('time', tod_dim_name,'pfull','lat', 'lon')
            or dim_info==('time',tod_dim_name,'level', 'lat', 'lon')
            or dim_info==('time', tod_dim_name,'pstd', 'lat', 'lon')
            or dim_info==('time',tod_dim_name,'zstd', 'lat', 'lon')
            or dim_info==('time',tod_dim_name,'zagl', 'lat', 'lon')
            or dim_info==('time',tod_dim_name,'zgrid', 'lat', 'lon')):

                if dim_info[1] in ['pfull','level','pstd']:  self.vert_unit='Pa'
                if dim_info[1] in ['zagl','zstd']:  self.vert_unit='m'

                #Initialize dimensions
                levs=f.variables[dim_info[2]][:]

                t=f.variables['time'][:];Ls=np.squeeze(f.variables['areo'][:]);ti=np.arange(0,len(t))
                #For diurn file, change time_of_day(time,24,1) to time_of_day(time) at midnight UT
                if f_type=='diurn'and len(Ls.shape)>1:Ls=np.squeeze(Ls[:,0])
                t_stack=np.vstack((t,Ls)) #stack the time and ls array as one variable

                ti,temp_txt =get_time_index(t_req,Ls)
                if add_fdim:self.fdim_txt+=temp_txt
                lati,temp_txt =get_lat_index(lat_req,lat)
                if add_fdim:self.fdim_txt+=temp_txt
                loni,temp_txt =get_lon_index(lon_req,lon)
                if add_fdim:self.fdim_txt+=temp_txt
                zi,temp_txt =get_level_index(lev_req,levs)
                if add_fdim:self.fdim_txt+=temp_txt

                reshape_shape=[len(np.atleast_1d(ti)),len(np.atleast_1d(tod)),len(np.atleast_1d(zi)),\
                        len(np.atleast_1d(lati)),len(np.atleast_1d(loni))]

                var=f.variables[var_name][ti,:,zi,lati,loni].reshape(reshape_shape)
                f.close()

                w=area_weights_deg(var.shape,lat[lati])


                #('time','time_of_day', 'pfull', 'lat', 'lon')

                return tod,   np.nanmean(np.nanmean(np.nanmean(np.average(var,weights=w,axis=3),axis=3),axis=2),axis=0),var_info



    def exception_handler(self,e,ax):
        if debug:raise
        sys.stdout.write("\033[F");sys.stdout.write("\033[K")
        prYellow('*** Warning *** Attempting %s profile for %s: %s'%(self.plot_type,self.varfull,str(e)))
        ax.text(0.5, 0.5, 'ERROR:'+str(e),horizontalalignment='center',verticalalignment='center', \
            bbox=dict(boxstyle="round",ec=(1., 0.5, 0.5),fc=(1., 0.8, 0.8),),\
            transform=ax.transAxes,wrap=True,fontsize=16)

    def fig_init(self):
        #create figure
        if self.layout is None : #No layout is specified
            out=fig_layout(self.subID,self.nPan,vertical_page)
        else:
            out=np.append(self.layout,self.subID)

        if self.subID==1 and not self.addLine:
            fig= plt.figure(facecolor='white',figsize=(width_inch, height_inch)) #create figure if 1st panel
        if not self.addLine:
            ax = plt.subplot(out[0],out[1],out[2]) #nrow,ncol,subID
        else:

            ax=plt.gca()

        return ax

    def fig_save(self):

        #save the figure
        if  self.subID==self.nPan : #Last subplot
            if  self.subID==1: #1 plot
                if not '[' in self.varfull:
                    sensitive_name=self.varfull.split('{')[0].strip()  #add split '{' in case varfull contains layer, does not do anything otherwise
                else:
                    sensitive_name='expression_'+get_list_varfull(self.varfull)[0].split('{')[0].strip()
            else: #multi panel
                sensitive_name='multi_panel'

            self.fig_name=output_path+'/plots/'+sensitive_name+'.'+out_format
            self.fig_name=create_name(self.fig_name)

            if i_list< len(objectList)-1 and not objectList[i_list+1].addLine:
                plt.savefig(self.fig_name,dpi=my_dpi )
                if out_format!="pdf":print("Saved:" +self.fig_name)
            #Last subplot
            if i_list== len(objectList)-1 :
                plt.savefig(self.fig_name,dpi=my_dpi )
                if out_format!="pdf":print("Saved:" +self.fig_name)


    def do_plot(self):
        #create figure
        ax=self.fig_init()


        try:    #try to do the figure, will return the error otherwise

            xdata,var,var_info=self.data_loader_1D(self.varfull,self.plot_type)

            if self.legend:
                txt_label=self.legend
            else:
                txt_label=var_info+'\n'+self.fdim_txt[1:]#we remove the first coma ',' of fdim_txt to print to the new line


            if self.plot_type=='1D_lat':

                plt.plot(var,xdata,self.axis_opt1,lw=2,label=txt_label)
                plt.ylabel('Latitude',fontsize=label_size-self.nPan*label_factor)
                #Label is provided
                if self.axis_opt2:
                    plt.xlabel(self.axis_opt2,fontsize=label_size-self.nPan*label_factor)
                else:
                    plt.xlabel(var_info,fontsize=label_size-self.nPan*label_factor)

                ax.yaxis.set_major_locator(MultipleLocator(15))
                ax.yaxis.set_minor_locator(MultipleLocator(5))
                if self.Dlim:plt.ylim(self.Dlim)
                if self.Vlim:plt.xlim(self.Vlim)

            if self.plot_type=='1D_lon':
                lon180,var=shift_data(xdata,var)

                plt.plot(lon180,var,self.axis_opt1,lw=2,label=txt_label)
                plt.xlabel('Longitude',fontsize=label_size-self.nPan*label_factor)
                #Label is provided
                if self.axis_opt2:
                    plt.ylabel(self.axis_opt2,fontsize=label_size-self.nPan*label_factor)
                else:
                    plt.ylabel(var_info,fontsize=label_size-self.nPan*label_factor)

                ax.xaxis.set_major_locator(MultipleLocator(30))
                ax.xaxis.set_minor_locator(MultipleLocator(10))
                if self.Dlim:plt.xlim(self.Dlim)
                if self.Vlim:plt.ylim(self.Vlim)


            if self.plot_type=='1D_time':
                tim=xdata[0,:];Ls=xdata[1,:]
                # If simulations cover different years, those can be stacked instead of continueous
                if parser.parse_args().stack_year:Ls=np.mod(Ls,360)

                plt.plot(Ls,var,self.axis_opt1,lw=2,label=txt_label)

                #Label is provided
                if self.axis_opt2:
                    plt.ylabel(self.axis_opt2,fontsize=label_size-self.nPan*label_factor)
                else:
                    plt.ylabel(var_info,fontsize=label_size-self.nPan*label_factor)

                #Axis formatting
                if self.Vlim:plt.ylim(self.Vlim)

                if self.Dlim:
                    plt.xlim(self.Dlim) #TODO

                Ls_ticks = [item for item in ax.get_xticks()]
                labels = [item for item in ax.get_xticklabels()]

                for i in range(0,len(Ls_ticks)):
                    id=np.argmin(np.abs(Ls-Ls_ticks[i])) #find tmstep closest to this tick
                    labels[i]='Ls %g\nsol %i'%(np.mod(Ls_ticks[i],360.),tim[id])

                ax.set_xticklabels(labels)

            if self.plot_type=='1D_lev':

                plt.plot(var,xdata,self.axis_opt1,lw=2,label=txt_label)

                #Label is provided
                if self.axis_opt2:
                    plt.xlabel(self.axis_opt2,fontsize=label_size-self.nPan*label_factor)
                else:
                    plt.xlabel(var_info,fontsize=label_size-self.nPan*label_factor)


                if self.vert_unit=='Pa':
                    ax.set_yscale("log")
                    ax.invert_yaxis()
                    ylabel_txt='Pressure [Pa]'
                else:
                    ylabel_txt='Altitude [m]'

                plt.ylabel(ylabel_txt,fontsize=label_size-self.nPan*label_factor)

                if self.Dlim:plt.ylim(self.Dlim)
                if self.Vlim:plt.xlim(self.Vlim)

            if self.plot_type=='1D_diurn':
                plt.plot(xdata,var,self.axis_opt1,lw=2,label=txt_label)
                plt.xlabel('Time [hr]',fontsize=label_size-self.nPan*label_factor)

                #Label is provided
                if self.axis_opt2:
                    plt.ylabel(self.axis_opt2,fontsize=label_size-self.nPan*label_factor)
                else:
                    plt.ylabel(var_info,fontsize=label_size-self.nPan*label_factor)

                ax.xaxis.set_major_locator(MultipleLocator(4))
                ax.xaxis.set_minor_locator(MultipleLocator(1))
                plt.xlim([0,24]) #by default, set xdim to 0-24, this may be overwritten

                #Axis formatting
                if self.Dlim:plt.xlim(self.Dlim)
                if self.Vlim:plt.ylim(self.Vlim)


            #====comon labelling====
            plt.xticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.yticks(fontsize=label_size-self.nPan*label_factor, rotation=0)
            plt.legend(fontsize=label_size-self.nPan*label_factor)
            plt.grid(True)


            self.success=True
        except Exception as e: #Return the error
            self.exception_handler(e,ax)
        self.fig_save()

#======================================================
#                  END OF PROGRAM
#======================================================

if __name__ == '__main__':
    main()
