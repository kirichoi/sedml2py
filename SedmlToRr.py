# usage:
#
# import SedmlToRr as s2p
# ret = s2p.sedml_to_python("full_path/sedml_file.sedml")
# exec ret
#
# import SedmlToRr as s2p
# ret = s2p.sedml_to_python("full_path/sedml_file.sedx")
# exec ret
#
# the .sedml extension indicates a sedml file, the .sedx extension indicates a sedml archive

import sys
import os.path
import re
import libsedml  # C:\WinPython-32bit-2.7.5.3\python-2.7.5\Lib\site-packages\libsedml\libsedml.py
import roadrunner
import roadrunner.testing
import zipfile, traceback
from os.path import isdir, join, normpath, split
from collections import namedtuple
MatchingSetsOfVariableIDs = namedtuple("MatchingSetsOfVariableIDs", "datagenID, taskReference, sedmlID, sbmlID")
MatchingSetsOfRepeatedTasksDataGenerators = namedtuple("MatchingSetsOfRepeatedTasksDataGenerators", "datagenID, rangeSize")


# Entry point
def sedml_to_python(fullPathName):      # full path name to SedML model
  from os.path import basename


  sedmlDoc = libsedml.readSedML(fullPathName)
  for e in range(0,sedmlDoc.getNumTasks()):
    task = sedmlDoc.getTask(e)
    print(task)
 

  modelName = os.path.splitext(basename(fullPathName))[0]
  extension = os.path.splitext(basename(fullPathName))[1]
  path = fullPathName.rsplit(basename(fullPathName),1)[0]

  class Tee(object):
    def __init__(self, *files):
      self.files = files
    def write(self, obj):
      for f in self.files:
        f.write(obj)

  if(extension == ".sedx"):
    import unzipy as uz
    zip = zipfile.ZipFile(fullPathName, 'r')
    path = path + modelName
    uz.unZip(path, zip)
    zip.close()
    fullPathName = uz.readManifest(path + "/manifest.xml")
    k = fullPathName.rfind("/")
    fullPathName = fullPathName[k+1:]
    fullPathName = path + "/" + fullPathName;

  sedmlDoc = libsedml.readSedML(fullPathName)
  if (sedmlDoc.getErrorLog().getNumFailsWithSeverity(libsedml.LIBSEDML_SEV_ERROR) > 0):  
    print(sedmlDoc.getErrorLog().toString())
    sys.exit(2)

  import StringIO
  f = StringIO.StringIO()
  original = sys.stdout
  sys.stdout = Tee(sys.stdout, f)   # output to console and file
  #sys.stdout = Tee(f)              # output to file only

  print("# Begin of generated script")
  print("import roadrunner")
  print("import roadrunner.testing")
  print("")
  for i in range(0, sedmlDoc.getNumModels()):
    currentModel = sedmlDoc.getModel(i)
    print("# Execute the tasks of model " + currentModel.getName())
    rrName = "rr" + str(i)
    print(rrName + " = roadrunner.RoadRunner()")
    generateTasks(rrName, sedmlDoc, currentModel, path)
    print("")
  print("# The Data Generators")
  dataGeneratorsList = []
  for i in range(0, sedmlDoc.getNumModels()):
    currentModel = sedmlDoc.getModel(i)
    generateData(sedmlDoc, currentModel, dataGeneratorsList)
    print("")
  print("# The Plots")
  generatePlots(sedmlDoc, dataGeneratorsList)
  print("# End of generated script\n")
  
  contents = f.getvalue()
  sys.stdout = original  # restore print to stdout only
  f.close()
  return (contents)


def generateTasks(rrName, sedmlDoc, currentModel, path):
  
  loadModel(rrName, sedmlDoc, currentModel, path)
  print(rrName + ".simulateOptions.structuredResult = False")

  for i in range(0, currentModel.getNumChanges()):
    aChange = currentModel.getChange(i)
    if(aChange.getElementName() == "changeAttribute"):
      newValue = aChange.getNewValue()
      variableName = aChange.getTarget()
      if(("model" in variableName) and ("parameter" in variableName)):
        pass
      elif(("model" in variableName) and ("species" in variableName)):
        pass
      else:
        print("# Unsupported changeAttribute target " + variableName)
        return          # nothing to do repeatedly since our change is bad
      variableName = variableName.rsplit("id=\'",1)[1]
      variableName = variableName.rsplit("\'",1)[0]
      print(rrName + ".model[\"[" + variableName + "]\"] = " + newValue)                   # set amount
    else:
      print("# Unsupported change " + aChange.getElementName() + " for model " + currentModel.getId())
      return

  # The 'selections' are a list of all the 'variable' elements from the dataGenerators
  for e in range(0,sedmlDoc.getNumTasks()):
    task1 = sedmlDoc.getTask(e)
    if(task1.getElementName() == "repeatedTask"):
      for i in range(0, task1.getNumSubTasks()):
        task2 = task1.getSubTask(i)     # the subtask which points to the real task we need to call repeatedly for each value in range
        task2 = task2.getTask()         # the Id of the real task
        task2 = sedmlDoc.getTask(task2) # get real task by Id
        if(task2.getModelReference() != currentModel.getId()):
          continue
        aRange = task1.getRange(0)       # we assume one single master range - we don't know how to deel flatten
        if(aRange.getElementName() != "uniformRange"):
          print("# Only uniformRange ranges are supported at this time")
          continue

        # need to use the RepeatedTask because the data generators refer to it 
        variablesDictionary = []      # matching pairs of sedml variable ID and sbml variable ID
        variablesList = []            # the IDs of the sbml variables, non duplicate entries
        populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary)
        # iterate over all changes
        aChange = task1.getTaskChange(0)
        if(aChange.getElementName() != "setValue"):
          print("# Only setValue changes are supported at this time")
          continue
        variableName = aChange.getTarget()
        vn = variableName
        vn = vn.rsplit("id=\'",1)[1]
        vn = vn.rsplit("\'",1)[0]
        # for each point in the range we compute the new values of the variables affected
        # and generate a task
        for j in range(0, aRange.getNumberOfPoints()):
          print("")
          start = aRange.getStart()
          end = aRange.getEnd()
          newValue = start + j * (end - start) / (aRange.getNumberOfPoints()-1)
          if(("model" in variableName) and ("parameter" in variableName)):
            pass
          elif(("model" in variableName) and ("species" in variableName)):
            pass
          else:
            print("# Unsupported setValue target " + variableName)
            return          # nothing to do repeatedly since our change is bad
          print(rrName + ".model[\"[" + vn + "]\"] = " + str(newValue))                   # set amount
          # need to use both the real Task (task2) because it has the reference to model and simulation 
          # and the repeated task (task1) because its Id is used for generating the flattened Id's
          generateSimulation(rrName, sedmlDoc, currentModel, task2, variablesList, variablesDictionary, j, task1)

    else:       # not a repeated task
      if(task1.getModelReference() != currentModel.getId()):
        continue
      variablesDictionary = []
      variablesList = []
      populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary)
      if(len(variablesList) == 0):
        continue
      generateSimulation(rrName, sedmlDoc, currentModel, task1, variablesList, variablesDictionary, -1)


def loadModel(rrName, sedmlDoc, currentModel, path):
  string = currentModel.getSource()
  if(isId(string)):                             # it's the Id of a model
    originalModel = sedmlDoc.getModel(string)
    string = originalModel.getSource()          #  !!! for now, we reuse the original model to which the current model is referring to

  if string.startswith("../"):                  # relative location, we trust it but need it trimmed
    string = string[3:]

    print(rrName + ".load('" + path + "/" + string + "')")    # SBML model name recovered from "source" attr
    #from os.path import expanduser
    #path = expanduser("~")
    #print(rrName + ".load('" + path + "\\" + string + "')")    # SBML model name recovered from "source" attr
  elif string.startswith("urn:miriam"):
    astr = string.rsplit(':', 1)
    astr = astr[1]
    import httplib
    conn = httplib.HTTPConnection("www.ebi.ac.uk")
    conn.request("GET", "/biomodels-main/download?mid=" + astr)
    r1 = conn.getresponse()
    #print(r1.status, r1.reason)
    data1 = r1.read()
    conn.close()
    string = "SBMLModels/" + modelName + ".xml"
    f1 = open(outDir + "/" + string, 'w')
    f1.write(data1);
    f1.close()
    print(rrName + ".load(roadrunner.testing.get_data('" + string +"'))")
  else:         # assume absolute path pointing to hard disk location
    string = string.replace("\\", "/")
    print(rrName + ".load('" + string + "')") 


def populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary):

  for i in range(0,  sedmlDoc.getNumDataGenerators()):
    current = sedmlDoc.getDataGenerator(i)
    vl = current.getListOfVariables()
    for j in range(0, vl.size()):
      currentVar = vl[j]
      if(currentVar.getTaskReference() != task1.getId()):
        continue
      if (currentVar.isSetSymbol()):    # symbol field of variable is set
        cvs = currentVar.getSymbol()
        astr = cvs.rsplit("symbol:")
        astr = astr[1]
        if(variablesList.count(astr) < 1):
          variablesList.append(astr)
        m = MatchingSetsOfVariableIDs(current.getId(), currentVar.getTaskReference(), currentVar.getId(), astr)
        #print m
        variablesDictionary.append(m)
      elif (currentVar.isSetTarget()):
        cvt = currentVar.getTarget()    # target field of variable is set
        astr = cvt.rsplit("@id='")
        astr = astr[1]
        astr = astr[:-2]
        if(variablesList.count(astr) < 1):
          variablesList.append(astr)
        m = MatchingSetsOfVariableIDs(current.getId(), currentVar.getTaskReference(), currentVar.getId(), astr)
        variablesDictionary.append(m)
      else:
        print("# Unrecognized data generator variable")
        sys.exit(5)
  return


def generateSimulation(rrName, sedmlDoc, currentModel, task1, variablesList, variablesDictionary, repeatedTaskIndex, repeatedTask = None):

  string = rrName + ".selections = ["
  for i in range(0, len(variablesList)):
    if i > 0:
      string += ","
    string += "\"" + variablesList[i] + "\""
  string += "]"
  print(string)

  for j  in range(0, sedmlDoc.getNumSimulations()):
    currentSimulation = sedmlDoc.getSimulation(j)
    if(task1.getSimulationReference() != currentSimulation.getId()):
      continue;
    if (currentSimulation.getTypeCode() == libsedml.SEDML_SIMULATION_UNIFORMTIMECOURSE):
      algorithm = currentSimulation.getAlgorithm()
      if(currentSimulation.isSetAlgorithm() == False):
        print("# Algorithm not set for simulation " + currentSimulation.getName())
        continue
      if(algorithm.getKisaoID() != "KISAO:0000019"):
        print("# Unsupported KisaoID " + algorithm.getKisaoID() + " for simulation " + currentSimulation.getName())
        continue

      if(repeatedTaskIndex == -1):    # we expand the repeatedTask id because they need to be flattened for each element in ranges
        taskId = task1.getId()
      else:
        taskId = repeatedTask.getId() + "_" + str(repeatedTaskIndex)
      string = taskId + " = " + rrName + ".simulate("
      tc = currentSimulation
      totNumPoints = tc.getOutputEndTime() * tc.getNumberOfPoints() / (tc.getOutputEndTime() - tc.getOutputStartTime())
      string += str(int(0)) + ", " + str(int(tc.getOutputEndTime())) + ", " + str(int(totNumPoints))
      string += ")"
      print(string)
    else:
      print("# Unsupported type " + currentSimulation.getTypeCode() + " for simulation " + currentSimulation.getName())


def generateData(sedmlDoc, currentModel, dataGeneratorsList):

  #from collections import namedtuple
  #MatchingSetsOfVariableIDs = namedtuple("MatchingSetsOfVariableIDs", "datagenID, taskReference, sedmlID, sbmlID")
  variablesDictionary = []      # matching pairs of sedml variable ID and sbml variable ID
  variablesList = []            # the IDs of the sbml variables, non duplicate entries

  for e in range(0,sedmlDoc.getNumTasks()):
    task1 = sedmlDoc.getTask(e)
    if(task1.getElementName() == "repeatedTask"):
      for i in range(0, task1.getNumSubTasks()):
        task2 = task1.getSubTask(i)     # the subtask which points to the real task we need to call repeatedly for each value in range
        task2 = task2.getTask()         # the Id of the real task
        task2 = sedmlDoc.getTask(task2) # get real task by Id
        if(task2.getModelReference() != currentModel.getId()):
          continue
        aRange = task1.getRange(0)       # we assume one single master range - we don't know how to deel flatten
        if(aRange.getElementName() != "uniformRange"):
          print("# Only uniformRange ranges are supported at this time")
          continue

        variablesDictionary = []
        variablesList = []
        # need to use the RepeatedTask because the data generators refer to it 
        populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary)
        # for each point in the range we compute the new values of the variables affected
        # and generate a task
        for j in range(0, aRange.getNumberOfPoints()):
          print("")
          # need to use both the real Task (task2) because it has the reference to model and simulation 
          # and the repeated task (task1) because its Id is used for generating the flattened Id's
          generateDataLoop(sedmlDoc, currentModel, task2, variablesList, variablesDictionary, j, task1, dataGeneratorsList)

    else:       # not a repeated task
      if(task1.getModelReference() != currentModel.getId()):
        continue
      variablesDictionary = []
      variablesList = []
      populateVariableLists(sedmlDoc, task1, variablesList, variablesDictionary)
      if(len(variablesList) == 0):
        continue
      generateDataLoop(sedmlDoc, currentModel, task1, variablesList, variablesDictionary, -1)




def generateDataLoop(sedmlDoc, currentModel, task1, variablesList, variablesDictionary, repeatedTaskIndex, repeatedTask = None, dataGeneratorsList = None):

  # Each dataGenerator is calculated from the resulting output
  for s in range(0, sedmlDoc.getNumSimulations()):
    currentSimulation = sedmlDoc.getSimulation(s)
    if(task1.getSimulationReference() == currentSimulation.getId()):
      break;            # we found the simulation referred to by this task

  for j in range (0, len(variablesDictionary)):
    m = variablesDictionary[j]
    current = sedmlDoc.getDataGenerator(m.datagenID)
    dataGeneratorResult = libsedml.formulaToString(current.getMath())

#    if((current.getId() == m.datagenID) and (task1.getId() == m.taskReference)):
    if(current.getId() == m.datagenID):
      stringToReplace = m.sedmlID
      position = m.sbmlID
      for k in range(0, len(variablesList)):
        if (position == variablesList[k]):
          position = k
          break
      if(repeatedTaskIndex == -1):
        taskId = task1.getId()
      else:
        taskId = repeatedTask.getId() + "_" + str(repeatedTaskIndex)
      if (currentSimulation.getTypeCode() == libsedml.SEDML_SIMULATION_UNIFORMTIMECOURSE):
        tc = currentSimulation
        totNumPoints = tc.getOutputEndTime() * tc.getNumberOfPoints() / (tc.getOutputEndTime() - tc.getOutputStartTime())
        replacementString = taskId + "[" + str(totNumPoints - currentSimulation.getNumberOfPoints()) + ":," + str(position) + "]"
      else:
        print("# Unsupported type " + currentSimulation.getTypeCode() + " for simulation " + currentSimulation.getName())
      dataGeneratorResult = dataGeneratorResult.replace(stringToReplace, replacementString)

      dataGeneratorId = current.getId()       # we expand the datagen id because they need to be flattened for repeated tasks
      if(repeatedTaskIndex != -1):
        dataGeneratorId += "_" + str(repeatedTaskIndex)
      dataGeneratorResult = dataGeneratorId + " = " + dataGeneratorResult
      print(dataGeneratorResult)

      if(repeatedTaskIndex != -1):      # list of data generators flattening (when part of a range)
        position = -1
        for i in range (0, len(dataGeneratorsList)):
          rtdg = dataGeneratorsList[i]
          if(rtdg.datagenID == current.getId()):   # already present
            position = i
            break
        if(position == -1):        # create it
          rtdg = MatchingSetsOfRepeatedTasksDataGenerators(current.getId(), repeatedTaskIndex+1 )
          dataGeneratorsList.append(rtdg)
        else:
          rtdg = MatchingSetsOfRepeatedTasksDataGenerators(current.getId(), repeatedTaskIndex+1 )
          dataGeneratorsList[position] = rtdg



def generatePlots(sedmlDoc, dataGeneratorsList):
  #The 'plot' output, minus the legend
  print("import numpy")
  print("import matplotlib.pyplot as plt")

  for i in range(0, sedmlDoc.getNumOutputs()):
    output = sedmlDoc.getOutput(i)
    typeCode = output.getTypeCode()
    if typeCode == libsedml.SEDML_OUTPUT_REPORT:
      print("# Unsupported output type.")
      #print("\tReport id=" , output.getId() , " numDataSets=" , output.getNumDataSets())
    elif typeCode == libsedml.SEDML_OUTPUT_PLOT2D:
      if output.getNumCurves() > 1:
        allX = "allX = numpy.array(["
        allY = "allY = numpy.array(["

        for j in range(0, output.getNumCurves()):
          curve = output.getCurve(j)
          xDataReference = curve.getXDataReference()
          yDataReference = curve.getYDataReference()

          position = -1
          for i in range (0, len(dataGeneratorsList)):
            rtdg = dataGeneratorsList[i]
            if(rtdg.datagenID == xDataReference):   # if we find a repeated task on X we'll just assume the same for Y
              position = i
              break
          if(position == -1):        # not in list
            allX += xDataReference + ","
            allY += yDataReference + ","
          else:                     # replace the single repeated task data generator with the set of flattened ones
            count = dataGeneratorsList[position].rangeSize
            for k in range (0, count):
              allX += xDataReference + "_" + str(k) + ","
              allY += yDataReference + "_" + str(k) + ","

        allX = allX[:-1] + "]).T"
        allY = allY[:-1] + "]).T"
        print(allX)
        print(allY)
        print("plt.plot(allX, allY)")
    elif typeCode == libsedml.SEDML_OUTPUT_PLOT3D:
      print("# 3D plots unsupported at this time.")
      #print("\tPlot3d id=" , output.getId() , " numSurfaces=" , output.getNumSurfaces())
    else:
      print("# Unsupported output type.")
    print("plt.show()")




def main(args):

  if len(args) != 3:
    print(main.__doc__)
    sys.exit(1)

  outDir = args[1]
  modelName = args[2]

  sedml_to_python2(outDir, modelName)
  
def sedml_to_python2(outDir, modelName):
    
  class Tee(object):
    def __init__(self, *files):
      self.files = files
    def write(self, obj):
      for f in self.files:
        f.write(obj)

  sedmlDoc = libsedml.readSedML(outDir + "/SedMLModels/" + modelName + ".sedml")      # try the sedml extension first, then try the more generic xml
  if (sedmlDoc.getErrorLog().getNumFailsWithSeverity(libsedml.LIBSEDML_SEV_ERROR) > 0):
    sedmlDoc = libsedml.readSedML(outDir + "/SedMLModels/" + modelName + ".xml")      # "/SedMLModels/"
    if (sedmlDoc.getErrorLog().getNumFailsWithSeverity(libsedml.LIBSEDML_SEV_ERROR) > 0):
      errorString = sedmlDoc.getErrorLog().toString()
      print(errorString)
      sys.exit(2)

  f = open(outDir + "/" + modelName + '.py', 'w+')   # print to both console and file
  original = sys.stdout
  sys.stdout = Tee(sys.stdout, f)

  for i in range(0, sedmlDoc.getNumModels()):
    currentModel = sedmlDoc.getModel(i)
    doWork(sedmlDoc, currentModel)

  sys.stdout = original                         # restore print to stdout only
  f.close()
  print("Finished file creation")

  string = outDir + "/" + modelName + ".py"     # run the file generated above
  execfile(string)

def isId(string):
  regular = re.compile('[\\/:-]')               # a SedML Id cannot contain these characters
  if regular.search(string):
    return False
  else:
    return True



sedmlFilesList = []
sedmlFilesList.append("BIOMD0000000021")        # works as is
sedmlFilesList.append("app2sim")                # exported from vCell
sedmlFilesList.append("asedml3repeat")          # exported from vCell (parameter scan)


if __name__ == '__main__':
   #main(sys.argv)
   main(["SedmlToRr", "C:/WinPython-32bit-2.7.5.3/python-2.7.5/Lib/site-packages/roadrunner/testing", sedmlFilesList[3]])
   #main(["SedmlToRr", "C:/TEMP", "asedml1"])

