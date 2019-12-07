#!/usr/bin/env python

from hardware import *
import log

RUNNING= 'RUNNING'
TERMINATED= 'TERMINATED'
WAITING= 'WAITING'
NEW= 'NEW'
READY = 'READY'


## emulates a compiled program
class Program():

    def __init__(self, name, instructions):
        self._name = name
        self._instructions = self.expand(instructions)

    @property
    def name(self):
        return self._name

    @property
    def instructions(self):
        return self._instructions

    def addInstr(self, instruction):
        self._instructions.append(instruction)

    def expand(self, instructions):
        expanded = []
        for i in instructions:
            if isinstance(i, list):
                ## is a list of instructions
                expanded.extend(i)
            else:
                ## a single instr (a String)
                expanded.append(i)

        ## now test if last instruction is EXIT
        ## if not... add an EXIT as final instruction
        last = expanded[-1]
        if not ASM.isEXIT(last):
            expanded.append(INSTRUCTION_EXIT)

        return expanded

    def __repr__(self):
        return "Program({name}, {instructions})".format(name=self._name, instructions=self._instructions)


## emulates an Input/Output device controller (driver)
class IoDeviceController():

    def __init__(self, device):
        self._device = device
        self._waiting_queue = []
        self._currentPCB = None


    def runOperation(self, pcb, instruction):
        pair = {'pcb': pcb, 'instruction': instruction}
        pcb.state = WAITING
        
        if HARDWARE.ioDevice.is_idle : 
            self._device.execute(instruction)
            self._currentPCB = pcb
        else:    
            self._waiting_queue.append(pair)
        

    def getFinishedPCB(self):
        finishedPCB = self._currentPCB
        self._currentPCB = None
        return finishedPCB

    
    def sacarYEjecutar(self):
        if (len(self._waiting_queue) > 0) and self._device.is_idle:
            pair = self._waiting_queue.pop(0)
            #print(pair)
            pcb = pair['pcb']
            instruction = pair['instruction']
            self._currentPCB = pcb
            self._device.execute(instruction)


    def __repr__(self):
        return "IoDeviceController for {deviceID} running: {currentPCB} waiting: {waiting_queue}".format(deviceID=self._device.deviceId, currentPCB=self._currentPCB, waiting_queue=self._waiting_queue)

class waiting_queue():
    def __init__(self):
        self.pcbs = []
    
    def agregar(self,dic):
        self.pcbs.append(dic)

    def sacar(self):
        return self.pcbs.pop(0)
    def isEmpty(self):
        return len(self.pcbs) == 0

    
## emulates the  Interruptions Handlers
class AbstractInterruptionHandler():
    def __init__(self, kernel):
        self._kernel = kernel

    @property
    def kernel(self):
        return self._kernel

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))


class KillInterruptionHandler(AbstractInterruptionHandler):

   def execute(self, irq):
        log.logger.info(" Program Finished ")
        log.logger.info(" que hay:{} ".format(irq))
        


        if self.kernel.pcbTable.pcbEnRunning() != None:
            procesosCorriendo = self.kernel.pcbTable.pcbEnRunning()
            procesosCorriendo.state = TERMINATED
            self.kernel.dispatcher.save(procesosCorriendo)

        if len(self.kernel.schaduler.hayElementosEnReadyQueve()) >= 1:

            next_pcb = self.kernel.schaduler.next()
            self.kernel.dispatcher.load(next_pcb)
        elif self.kernel.pcbTable.todosLosProcesosTerminaron():
            HARDWARE.switchOff()
            log.logger.info("\n Gantt: {}".format(self.kernel.gantt))
       
                
class IoInInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        operation = irq.parameters
        pcbRunning = self.kernel.pcbTable.pcbEnRunning()

        self.kernel.dispatcher.save(pcbRunning)

        self.kernel.ioDeviceController.runOperation(pcbRunning,operation)

        if len(self.kernel.schaduler.hayElementosEnReadyQueve()) >= 1:
            next_pcb = self.kernel.schaduler.next()
            self.kernel.dispatcher.load(next_pcb)

        log.logger.info(self.kernel.ioDeviceController)

class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pcb = self.kernel.ioDeviceController.getFinishedPCB()
        self._kernel.ioDeviceController.sacarYEjecutar()
        self.kernel.schaduler.add(pcb)
        
        log.logger.info(self.kernel.ioDeviceController)
class HandlerTime(AbstractInterruptionHandler):

    def execute(self, irq):
        if len(self.kernel.schaduler.hayElementosEnReadyQueve()) >= 1:
            if self.kernel.pcbTable.pcbEnRunning() != None:
                pcbCorriendo = self.kernel.pcbTable.pcbEnRunning()
                self.kernel.schaduler.expropiar(pcbCorriendo)
                
        HARDWARE.timer.reset()

class NewHandler(AbstractInterruptionHandler):

   def execute(self,irq):
        program = irq.parameters["program"]
        prioridad = irq.parameters["prioridad"]
  
        baseDir = self._kernel.loader.load(program)
        pcb = PCB(baseDir,program,prioridad)
        self.kernel.pcbTable.cagarPcb(pcb)
        
        self.kernel.schaduler.add(pcb)

       
        log.logger.info("\n Executing program: {name}".format(name=program.name))
        log.logger.info("\n diccionario: {pcbTable}".format(pcbTable=pcb))
        log.logger.info(HARDWARE)

# emulates the core of an Operative System
class Kernel():

    def __init__(self):
        self.loader = Loader()  
        self.pcbTable = PCBTable()
        self.dispatcher = Dispatcher()
        
        # self.schaduler = FCFS(self)
        # self.schaduler = PrioridadNoExpropiativa(self)
        self.schaduler = PrioridadExpropiativa(self)
        # self.schaduler = Roundribin(self)
        # HARDWARE.timer.quantum=3
        
        self.gantt = Gantt(self)
        HARDWARE.clock.addSubscriber(self.gantt)
        

        killHandler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, killHandler)

        ioInHandler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, ioInHandler)

        ioOutHandler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, ioOutHandler)

        newInterruptionHandler = NewHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE,newInterruptionHandler)
        
        handlerTime = HandlerTime(self)
        HARDWARE.interruptVector.register(TIMEOUT_INTERRUPTION_TYPE,handlerTime)
       
        ## controls the Hardware's I/O Device
        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)
             

    @property
    def ioDeviceController(self):
        return self._ioDeviceController
    
    def executeBatch (self,batch):
        programa = batch
        for x in  programa:
             self.run(x) 


    ## emulates a "system call" for programs execution
    def run(self, program,prioridad):
        New = IRQ(NEW_INTERRUPTION_TYPE,{"program":program,"prioridad":prioridad})
        HARDWARE.interruptVector.handle(New)



    def __repr__(self):
        return "Kernel "
class Loader():
    def __init__ (self):
        self.indiceDecarga = 0
     
    def load (self, program):
        progSize = len(program.instructions)
        for index in range(0, progSize):
            inst = program.instructions[index]
            HARDWARE.memory.write(index + self.indiceDecarga, inst)
        self.indiceDecarga += progSize
        return self.indiceDecarga - progSize


class PCB():
    def __init__(self,base,program,prioridad):
        self.baseDir = base
        self.programPath = program.name
        self.pid = 0
        self.pc = 0
        self.state = NEW
        self.prioridad = prioridad
    def __repr__(self):
        return "pid {} baseDir {} pc {} state {} programPath {}".format(self.pid,self.baseDir,self.pc,self.state,self.programPath)

class PCBTable():
    def __init__(self):
        self.procesos = {}
        self.pid = 0 
    
    def __repr__(self):
        return tabulate(enumerate(self.procesos), tablefmt='psql')

    def cagarPcb(self,pcb):
        pidNuevo = self.pid
        self.procesos[pidNuevo] = pcb
        pcb.pid = self.pid
        self.pid +=1

    def pcbEnRunning (self):
        for k,v in  self.procesos.items():
            if v.state == RUNNING:
                return v 
        return None

    def todosLosProcesosTerminaron (self):
        for k,v in  self.procesos.items():
            if v.state != TERMINATED:
                return False
             
        return True
                
    
class Dispatcher():

    def load(self, pcb):
        HARDWARE.cpu.pc = pcb.pc
        HARDWARE.mmu.baseDir = pcb.baseDir
        HARDWARE.timer.reset()
        pcb.state = RUNNING
    
    def save(self, pcb):
        pcb.pc = HARDWARE.cpu.pc
        HARDWARE.cpu.pc = -1

class Gantt():
   
    def __init__(self,kernel):
        self._ticks = []
        self._kernel = kernel
   
    def tick (self,tickNbr):
        log.logger.info("guardando informacion de los estados de los PCBs en el tick N {}".format(tickNbr))
        pcbYEstado = dict()
        pcbTable = self._kernel.pcbTable.procesos

        for pid,pcb in pcbTable.items():
            pcbYEstado[pid] = pcb.state
        self._ticks.append(pcbYEstado)
           
    def __repr__(self):
        return tabulate(enumerate(self._ticks), tablefmt='grid')

class readyQueve():
    def __init__(self):
        self.pcbs = []
    def insert(self,indice,pcb):
        pcb.state = READY
        self.pcbs.insert(indice,pcb)
    def agregar (self,pcb):
        pcb.state = READY
        self.pcbs.append(pcb)
    def sacar (self):
        return self.pcbs.pop(0)

    def elementosDeLista(self):
        return self.pcbs

class Schaduler():
    
    def __init__(self,kernel):
        self.readyQueve = readyQueve()
        self.kernel = kernel
    def add (self):
        pass
    def expropiar(self,pcb):
        pass
    def next (self):
        return self.readyQueve.sacar()
    def hayElementosEnReadyQueve(self):
        return self.readyQueve.elementosDeLista()
    def enColarOrdenado(self,pcb):
        index = 0
        while index < len(self.readyQueve.pcbs) and self.readyQueve.pcbs[index].prioridad < pcb.prioridad:
            index = index + 1
        self.readyQueve.insert(index,pcb)

class FCFS(Schaduler):

    def add (self,pcb):
        if self.kernel.pcbTable.pcbEnRunning() == None:
            self.kernel.dispatcher.load(pcb)
        else:
            self.readyQueve.agregar(pcb)


class PrioridadNoExpropiativa(Schaduler):
    def add (self,pcb):

        if  self.kernel.pcbTable.pcbEnRunning() == None:
            self.kernel.dispatcher.load(pcb)
        else:
            self.enColarOrdenado(pcb)

class PrioridadExpropiativa(Schaduler):

    def add (self,pcb):
        if  self.kernel.pcbTable.pcbEnRunning() == None:
            self.kernel.dispatcher.load(pcb)
        else:
            self.expropiar(pcb)

    def expropiar(self,pcb):
        pcbCorriendo = self.kernel.pcbTable.pcbEnRunning()
       
        if(pcb.prioridad < pcbCorriendo.prioridad):
            self.kernel.dispatcher.save(pcbCorriendo)
            self.enColarOrdenado(pcbCorriendo)
            self.kernel.dispatcher.load(pcb)
        else:
            self.enColarOrdenado(pcb)
    
class Roundribin(Schaduler):
    def add (self,pcb):
        if self.kernel.pcbTable.pcbEnRunning() == None:
            self.kernel.dispatcher.load(pcb)
        else:
            self.readyQueve.agregar(pcb)
    def expropiar(self,pcb):
        if len(self.kernel.schaduler.hayElementosEnReadyQueve()) >= 1:
            if self.kernel.pcbTable.pcbEnRunning() != None:
                pcbCorriendo = self.kernel.pcbTable.pcbEnRunning()
                self.kernel.dispatcher.save(pcbCorriendo)
                self.add(pcbCorriendo)
                elSiguinete = self.next()
                self.kernel.dispatcher.load(elSiguinete)